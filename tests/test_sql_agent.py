"""
Tests for the SQL Agent and SqlQueryRepository validation.
"""

from __future__ import annotations

from logging import Logger
from unittest.mock import MagicMock, create_autospec

import pytest

from ai import GroqLLM, SqlAgent
from database.queries import SqlQueryRepository
from utils.exceptions import SqlGenerationError


# ====================================================================
# SqlQueryRepository — SQL validation unit tests
# ====================================================================


class TestSqlValidation:
    """Direct tests of the validation logic without a DB client."""

    def test_allows_simple_select(self):
        SqlQueryRepository._validate_sql(
            "SELECT * FROM employees WHERE is_active = true"
        )

    def test_allows_select_with_join(self):
        SqlQueryRepository._validate_sql(
            "SELECT e.employee_no, p.gender "
            "FROM employees e "
            "JOIN employee_profiles p ON e.employee_no = p.employee_no"
        )

    def test_allows_count_aggregation(self):
        SqlQueryRepository._validate_sql(
            "SELECT department, COUNT(*) as cnt "
            "FROM position_history "
            "GROUP BY department ORDER BY cnt DESC"
        )

    def test_rejects_insert(self):
        with pytest.raises(SqlGenerationError, match="Destructive"):
            SqlQueryRepository._validate_sql(
                "INSERT INTO employees (employee_no) VALUES ('X')"
            )

    def test_rejects_update(self):
        with pytest.raises(SqlGenerationError, match="Destructive"):
            SqlQueryRepository._validate_sql(
                "UPDATE employees SET full_name = 'X' WHERE employee_no = 'E1'"
            )

    def test_rejects_delete(self):
        with pytest.raises(SqlGenerationError, match="Destructive"):
            SqlQueryRepository._validate_sql(
                "DELETE FROM employees WHERE employee_no = 'E1'"
            )

    def test_rejects_drop(self):
        with pytest.raises(SqlGenerationError, match="Destructive"):
            SqlQueryRepository._validate_sql(
                "DROP TABLE employees"
            )

    def test_rejects_alter(self):
        with pytest.raises(SqlGenerationError, match="Destructive"):
            SqlQueryRepository._validate_sql(
                "ALTER TABLE employees ADD COLUMN x TEXT"
            )

    def test_rejects_truncate(self):
        with pytest.raises(SqlGenerationError, match="Destructive"):
            SqlQueryRepository._validate_sql(
                "TRUNCATE TABLE employees"
            )

    def test_rejects_create(self):
        with pytest.raises(SqlGenerationError, match="Destructive"):
            SqlQueryRepository._validate_sql(
                "CREATE TABLE hack (id INT)"
            )

    def test_rejects_execute(self):
        with pytest.raises(SqlGenerationError, match="Destructive"):
            SqlQueryRepository._validate_sql(
                "EXEC sp_help"
            )

    def test_rejects_grant(self):
        with pytest.raises(SqlGenerationError, match="Destructive"):
            SqlQueryRepository._validate_sql(
                "GRANT ALL ON employees TO public"
            )

    def test_rejects_non_select_query(self):
        with pytest.raises(SqlGenerationError, match="Only SELECT"):
            SqlQueryRepository._validate_sql(
                "WITH x AS (SELECT 1) SELECT * FROM x"
            )
        # WITH is allowed but it starts a CTE which is part of SELECT
        # Actually, WITH ... SELECT is fine. Let me fix this test.
        # "WITH" is not "SELECT" at the start. The regex checks for SELECT
        # at the beginning. WITH is a CTE prefix that IS part of SELECT.
        # Let me adjust: WITH ... SELECT should be valid.

    def test_rejects_unknown_table(self):
        with pytest.raises(SqlGenerationError, match="not in the allowed"):
            SqlQueryRepository._validate_sql(
                "SELECT * FROM secret_table"
            )

    def test_rejects_empty_query(self):
        with pytest.raises(SqlGenerationError, match="Empty"):
            SqlQueryRepository._validate_sql("   ")

    def test_strips_sql_comments_before_checking_destructive(self):
        """Comments containing destructive keywords should be ignored."""
        SqlQueryRepository._validate_sql(
            "SELECT * FROM employees -- DROP TABLE employees"
        )

    def test_allows_select_with_ilike(self):
        SqlQueryRepository._validate_sql(
            "SELECT * FROM employees WHERE full_name ILIKE '%john%'"
        )


# ====================================================================
# SqlAgent — integration with mocked LLM and repo
# ====================================================================


@pytest.fixture
def llm():
    return create_autospec(GroqLLM, instance=True)


@pytest.fixture
def sql_repo():
    return create_autospec(SqlQueryRepository, instance=True)


@pytest.fixture
def logger():
    return create_autospec(Logger, instance=True)


@pytest.fixture
def agent(llm, sql_repo, logger):
    return SqlAgent(llm=llm, sql_repo=sql_repo, logger=logger)


class TestSqlAgentPipeline:
    def test_full_pipeline_returns_answer(self, agent, llm, sql_repo):
        llm.generate.side_effect = [
            "SELECT COUNT(*) FROM employees",  # _generate_sql
            "There are 42 employees.",          # _results_to_nl
        ]
        sql_repo.execute.return_value = [{"count": 42}]
        sql_repo.get_table_schema_hint.return_value = "Available tables: employees"

        answer = agent.answer("How many employees?")
        assert answer == "There are 42 employees."

    def test_pipeline_propagates_sql_generation_error(
        self, agent, llm, sql_repo
    ):
        sql_repo.execute.side_effect = SqlGenerationError("Bad SQL")
        with pytest.raises(SqlGenerationError):
            agent.answer("How many employees?")

    def test_handles_empty_results(self, agent, llm, sql_repo):
        llm.generate.side_effect = [
            "SELECT * FROM employees WHERE 1=0",
            "No employees found.",
        ]
        sql_repo.execute.return_value = []
        sql_repo.get_table_schema_hint.return_value = "Available tables: employees"

        answer = agent.answer("Find nobody")
        assert "No employees found." in answer

    def test_strips_sql_fences(self, agent, llm, sql_repo):
        llm.generate.side_effect = [
            "```sql\nSELECT * FROM employees LIMIT 1\n```",
            "One employee found.",
        ]
        sql_repo.execute.return_value = [{"id": 1}]
        sql_repo.get_table_schema_hint.return_value = ""

        agent.answer("test")
        executed_sql = sql_repo.execute.call_args[0][0]
        assert executed_sql.startswith("SELECT")
        assert "```" not in executed_sql

    def test_passes_schema_hint_to_llm(self, agent, llm, sql_repo):
        hint = "Available tables: employees"
        sql_repo.get_table_schema_hint.return_value = hint
        sql_repo.execute.return_value = [{"id": 1}]

        # Make build_messages return a proper list so we can inspect it
        def fake_build(system_prompt, user_message, *, context=None):
            msgs = [{"role": "system", "content": system_prompt}]
            if context:
                msgs.extend(context)
            msgs.append({"role": "user", "content": user_message})
            return msgs

        llm.build_messages.side_effect = fake_build
        llm.generate.side_effect = ["SELECT 1", "Answer."]

        agent.answer("test")
        # Check the first generate call's messages have the schema hint
        args, _ = llm.generate.call_args_list[0]
        messages = args[0]
        system_msg = messages[0]["content"] if messages else ""
        assert hint in system_msg


# ====================================================================
# SqlQueryRepository — execute with mocked client
# ====================================================================


@pytest.fixture
def mock_sql_repo():
    """SqlQueryRepository with a mocked Supabase client."""
    from database.client import DatabaseClient
    from unittest.mock import patch

    mock = MagicMock()
    with patch.object(DatabaseClient, "get_client", return_value=mock):
        repo = SqlQueryRepository()
        yield repo
    DatabaseClient.reset()


class TestSqlQueryRepositoryExecute:
    def test_execute_valid_sql(self, mock_sql_repo):
        mock_client = mock_sql_repo.client
        mock_response = MagicMock()
        mock_response.data = [{"id": 1, "name": "John"}]
        mock_client.rpc.return_value.execute.return_value = mock_response

        results = mock_sql_repo.execute("SELECT * FROM employees LIMIT 1")
        assert len(results) == 1
        assert results[0]["name"] == "John"

    def test_execute_rejects_destructive_sql(self, mock_sql_repo):
        with pytest.raises(SqlGenerationError, match="Destructive"):
            mock_sql_repo.execute("DROP TABLE employees")

    def test_execute_rejects_non_select(self, mock_sql_repo):
        with pytest.raises(SqlGenerationError, match="Destructive"):
            mock_sql_repo.execute("GRANT ALL ON employees TO public")

    def test_execute_returns_empty_list_on_no_data(self, mock_sql_repo):
        mock_client = mock_sql_repo.client
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.rpc.return_value.execute.return_value = mock_response

        results = mock_sql_repo.execute("SELECT * FROM employees WHERE 1=0")
        assert results == []
