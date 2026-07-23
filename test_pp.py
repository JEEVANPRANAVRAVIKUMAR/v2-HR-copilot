from database.queries.employee_repository import EmployeeRepository

repo = EmployeeRepository()

print(repo.exists("EMP001"))

print(repo.get_by_employee_no("EMP001"))

print(repo.get_all())