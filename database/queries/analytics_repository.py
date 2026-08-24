"""
Analytics repository.

Provides workforce aggregation queries used by the Analytics
agent. Every method returns raw dicts — formatting and NL
explanation is handled upstream.

Aggregation is done in Python because the Supabase REST API
does not expose a raw SQL RPC. All data is fetched via the
standard Supabase client with nested selects (1:1 joins),
then grouped and tabulated in memory.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any, Dict, List

from database.queries.base_repository import BaseRepository
from utils.exceptions import RepositoryError


class AnalyticsRepository(BaseRepository):
    """
    Repository for workforce analytics queries.

    All complex aggregations are computed in Python from joined
    Supabase REST responses. No raw SQL RPC is used.
    """

    # ----------------------------------------------------------------
    # Headcount
    # ----------------------------------------------------------------

    def total_headcount(self) -> int:
        """
        Total number of active employees.
        """
        try:
            response = self._execute(
                self.client.table("employees")
                .select("employee_no", count="exact")
                .eq("is_active", True)
            )
            return response.count or 0
        except Exception as exc:
            self.logger.exception("Failed to get headcount.")
            raise RepositoryError("Unable to compute headcount.") from exc

    def headcount_by_department(self) -> List[Dict[str, Any]]:
        """
        Active employees grouped by department name.

        Uses nested select: employees → position_history → departments.
        Takes the department from the most recent position_history entry
        (sorted by start_date DESC) for each employee.
        """
        try:
            response = self._execute(
                self.client.table("employees")
                .select(
                    "employee_no,"
                    "position_history(department_id,start_date,departments(department_name))"
                )
                .eq("is_active", True)
            )
            if not self._has_data(response):
                return []

            dept_counter: dict[str, int] = {}
            for row in response.data:
                ph = row.get("position_history")
                if not ph:
                    continue
                ph_list = [ph] if isinstance(ph, dict) else (ph if isinstance(ph, list) else [])
                if len(ph_list) == 0:
                    continue
                # Get the most recent position
                sorted_ph = sorted(
                    ph_list,
                    key=lambda x: x.get("start_date", ""),
                    reverse=True,
                )
                latest = sorted_ph[0]
                depts = latest.get("departments")
                name = depts.get("department_name", "Unknown") if depts else "Unknown"
                dept_counter[name] = dept_counter.get(name, 0) + 1

            return sorted(
                [{"department": k, "count": v} for k, v in dept_counter.items()],
                key=lambda d: d["count"],
                reverse=True,
            )
        except Exception as exc:
            self.logger.exception("Failed to get headcount by department.")
            raise RepositoryError("Unable to compute department breakdown.") from exc

    def headcount_by_status(self) -> List[Dict[str, Any]]:
        """
        Employees grouped by employment status.
        """
        try:
            response = self._execute(
                self.client.table("employees")
                .select("employee_no,employment_details(status)")
                .eq("is_active", True)
            )
            if not self._has_data(response):
                return []

            status_counter: dict[str, int] = {}
            for row in response.data:
                ed = row.get("employment_details")
                if isinstance(ed, list) and len(ed) > 0:
                    ed = ed[0]
                st = (ed.get("status") or "Unknown") if isinstance(ed, dict) else "Unknown"
                status_counter[st] = status_counter.get(st, 0) + 1

            return sorted(
                [{"status": k, "count": v} for k, v in status_counter.items()],
                key=lambda d: d["count"],
                reverse=True,
            )
        except Exception as exc:
            self.logger.exception("Failed to get headcount by status.")
            raise RepositoryError("Unable to compute status breakdown.") from exc

    # ----------------------------------------------------------------
    # Hiring trends
    # ----------------------------------------------------------------

    def hiring_by_year(self) -> List[Dict[str, Any]]:
        """
        Hires per year based on joining_date.
        """
        try:
            response = self._execute(
                self.client.table("employees")
                .select("employee_no,employment_details(joining_date)")
            )
            if not self._has_data(response):
                return []

            year_counter: dict[int, int] = {}
            for row in response.data:
                ed = row.get("employment_details")
                if isinstance(ed, list) and len(ed) > 0:
                    ed = ed[0]
                if not isinstance(ed, dict):
                    continue
                jd = ed.get("joining_date")
                if jd is None:
                    continue
                if isinstance(jd, str):
                    jd = date.fromisoformat(jd)
                yr = jd.year if hasattr(jd, "year") else int(str(jd)[:4])
                year_counter[yr] = year_counter.get(yr, 0) + 1

            return sorted(
                [{"year": k, "hires": v} for k, v in year_counter.items()],
                key=lambda d: d["year"],
            )
        except Exception as exc:
            self.logger.exception("Failed to get hiring trends.")
            raise RepositoryError("Unable to compute hiring trends.") from exc

    def hiring_by_month(self) -> List[Dict[str, Any]]:
        """
        Hires per month (as label "YYYY-MM").
        """
        try:
            response = self._execute(
                self.client.table("employees")
                .select("employee_no,employment_details(joining_date)")
            )
            if not self._has_data(response):
                return []

            month_counter: dict[str, int] = {}
            for row in response.data:
                ed = row.get("employment_details")
                if isinstance(ed, list) and len(ed) > 0:
                    ed = ed[0]
                if not isinstance(ed, dict):
                    continue
                jd = ed.get("joining_date")
                if jd is None:
                    continue
                if isinstance(jd, str):
                    jd = date.fromisoformat(jd)
                label = f"{jd.year}-{jd.month:02d}" if hasattr(jd, "month") else str(jd)[:7]
                month_counter[label] = month_counter.get(label, 0) + 1

            return sorted(
                [{"month": k, "hires": v} for k, v in month_counter.items()],
                key=lambda d: d["month"],
            )
        except Exception as exc:
            self.logger.exception("Failed to get monthly hiring trends.")
            raise RepositoryError("Unable to compute monthly hiring trends.") from exc

    # ----------------------------------------------------------------
    # Tenure
    # ----------------------------------------------------------------

    def average_tenure_years(self) -> float:
        """
        Average tenure of active employees in years.
        """
        try:
            today = date.today()
            response = self._execute(
                self.client.table("employees")
                .select("employee_no,employment_details(joining_date)")
                .eq("is_active", True)
            )
            if not self._has_data(response):
                return 0.0

            tenures = []
            for row in response.data:
                ed = row.get("employment_details")
                if isinstance(ed, list) and len(ed) > 0:
                    ed = ed[0]
                if not isinstance(ed, dict):
                    continue
                jd = ed.get("joining_date")
                if jd is None:
                    continue
                if isinstance(jd, str):
                    jd = date.fromisoformat(jd)
                if hasattr(jd, "year"):
                    delta = today - jd
                    tenures.append(delta.days / 365.25)

            if not tenures:
                return 0.0
            return round(sum(tenures) / len(tenures), 2)
        except Exception as exc:
            self.logger.exception("Failed to compute average tenure.")
            raise RepositoryError("Unable to compute tenure.") from exc

    def tenure_distribution(self) -> List[Dict[str, Any]]:
        """
        Tenure buckets for active employees.
        """
        try:
            today = date.today()
            response = self._execute(
                self.client.table("employees")
                .select("employee_no,employment_details(joining_date)")
                .eq("is_active", True)
            )
            if not self._has_data(response):
                return []

            buckets: dict[str, int] = {
                "< 1 year": 0,
                "1-3 years": 0,
                "3-5 years": 0,
                "5-10 years": 0,
                "10+ years": 0,
            }
            bucket_order = ["< 1 year", "1-3 years", "3-5 years", "5-10 years", "10+ years"]

            for row in response.data:
                ed = row.get("employment_details")
                if isinstance(ed, list) and len(ed) > 0:
                    ed = ed[0]
                if not isinstance(ed, dict):
                    continue
                jd = ed.get("joining_date")
                if jd is None:
                    continue
                if isinstance(jd, str):
                    jd = date.fromisoformat(jd)
                if not hasattr(jd, "year"):
                    continue
                years = (today - jd).days / 365.25
                if years < 1:
                    label = "< 1 year"
                elif years < 3:
                    label = "1-3 years"
                elif years < 5:
                    label = "3-5 years"
                elif years < 10:
                    label = "5-10 years"
                else:
                    label = "10+ years"
                buckets[label] += 1

            return [
                {"bucket": b, "count": buckets[b]}
                for b in bucket_order
                if buckets[b] > 0
            ]
        except Exception as exc:
            self.logger.exception("Failed to compute tenure distribution.")
            raise RepositoryError("Unable to compute tenure distribution.") from exc

    # ----------------------------------------------------------------
    # Diversity
    # ----------------------------------------------------------------

    def gender_breakdown(self) -> List[Dict[str, Any]]:
        """
        Active employees grouped by gender.
        """
        try:
            response = self._execute(
                self.client.table("employees")
                .select("employee_no,employee_profiles(gender)")
                .eq("is_active", True)
            )
            if not self._has_data(response):
                return []

            gender_counter: dict[str, int] = {}
            for row in response.data:
                ep = row.get("employee_profiles")
                if isinstance(ep, list) and len(ep) > 0:
                    ep = ep[0]
                g = (ep.get("gender") or "Unknown") if isinstance(ep, dict) else "Unknown"
                gender_counter[g] = gender_counter.get(g, 0) + 1

            return sorted(
                [{"gender": k, "count": v} for k, v in gender_counter.items()],
                key=lambda d: d["count"],
                reverse=True,
            )
        except Exception as exc:
            self.logger.exception("Failed to get gender breakdown.")
            raise RepositoryError("Unable to compute gender breakdown.") from exc

    # ----------------------------------------------------------------
    # History-based time-series queries (Scope 5)
    # ----------------------------------------------------------------

    def fastest_growing_department(self) -> List[Dict[str, Any]]:
        """
        Department growth in absolute hires over the last 12 months.
        Falls back to employment_details.joining_date.
        """
        try:
            cutoff = date.today().replace(year=date.today().year - 1)
            response = self._execute(
                self.client.table("employees")
                .select(
                    "employee_no,"
                    "employment_details(joining_date),"
                    "position_history(department_id,start_date,departments(department_name))"
                )
                .eq("is_active", True)
            )
            if not self._has_data(response):
                return []

            dept_counter: dict[str, int] = {}
            for row in response.data:
                ed = row.get("employment_details")
                if isinstance(ed, list) and len(ed) > 0:
                    ed = ed[0]
                if not isinstance(ed, dict):
                    continue
                jd = ed.get("joining_date")
                if jd is None:
                    continue
                if isinstance(jd, str):
                    jd = date.fromisoformat(jd)
                if hasattr(jd, "year") and jd < cutoff:
                    continue

                ph = row.get("position_history")
                if not ph:
                    continue
                ph_list = [ph] if isinstance(ph, dict) else (ph if isinstance(ph, list) else [])
                if len(ph_list) == 0:
                    continue
                sorted_ph = sorted(
                    ph_list, key=lambda x: x.get("start_date", ""), reverse=True,
                )
                latest = sorted_ph[0]
                depts = latest.get("departments")
                name = depts.get("department_name", "Unknown") if depts else "Unknown"
                dept_counter[name] = dept_counter.get(name, 0) + 1

            return sorted(
                [{"department": k, "hires": v} for k, v in dept_counter.items()],
                key=lambda d: d["hires"],
                reverse=True,
            )
        except Exception as exc:
            self.logger.exception("Failed to get fastest growing department.")
            raise RepositoryError("Unable to compute department growth.") from exc

    def largest_engineering_hub(self) -> List[Dict[str, Any]]:
        """
        City with the most active employees.
        """
        try:
            response = self._execute(
                self.client.table("employees")
                .select("employee_no,addresses(city)")
                .eq("is_active", True)
            )
            if not self._has_data(response):
                return []

            city_counter: dict[str, int] = {}
            for row in response.data:
                addr = row.get("addresses")
                if isinstance(addr, list) and len(addr) > 0:
                    addr = addr[0]
                c = (addr.get("city") or "Unknown") if isinstance(addr, dict) else "Unknown"
                city_counter[c] = city_counter.get(c, 0) + 1

            return sorted(
                [{"city": k, "count": v} for k, v in city_counter.items()],
                key=lambda d: d["count"],
                reverse=True,
            )
        except Exception as exc:
            self.logger.exception("Failed to get the largest hub.")
            raise RepositoryError("Unable to compute largest hub.") from exc

    def understaffed_departments(
        self, threshold_pct: float = 10.0,
    ) -> List[Dict[str, Any]]:
        """
        Departments with headcount below threshold_pct of total.
        """
        try:
            total = self.total_headcount()
            if total == 0:
                return []
            dept = self.headcount_by_department()
            under = []
            for d in dept:
                cnt = d.get("count", 0)
                pct = cnt / total * 100
                if pct < threshold_pct:
                    under.append({
                        "department": d.get("department"),
                        "count": cnt,
                        "percent_of_total": round(pct, 1),
                    })
            return sorted(under, key=lambda d: d["count"])
        except Exception as exc:
            self.logger.exception("Failed to compute understaffed departments.")
            raise RepositoryError("Unable to compute understaffed departments.") from exc

    def hiring_forecast(self) -> Dict[str, Any]:
        """
        Projected future hires based on the 2-year trend.
        """
        try:
            rows = self.hiring_by_year()
            if not rows:
                return {
                    "year": [],
                    "hires": [],
                    "avg_hires_per_year": 0.0,
                    "projected_next_year_hires": 0.0,
                    "note": "Not enough history for a forecast.",
                }

            years = [int(r["year"]) for r in rows]
            hires = [int(r["hires"]) for r in rows]

            if len(hires) >= 2:
                avg = sum(hires[-2:]) / 2.0
            elif len(hires) == 1:
                avg = float(hires[0])
            else:
                avg = 0.0

            return {
                "year": years,
                "hires": hires,
                "avg_hires_per_year": round(avg, 1),
                "projected_next_year_hires": round(avg, 0),
                "note": (
                    "Based on the average of the last 2 years."
                    if len(hires) >= 2
                    else f"Only {len(hires)} year(s) of data available."
                ),
            }
        except Exception as exc:
            self.logger.exception("Failed to compute hiring forecast.")
            raise RepositoryError("Unable to compute hiring forecast.") from exc

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------

    def full_snapshot(self) -> Dict[str, Any]:
        """
        Run all analytics queries and return a single snapshot.
        """
        return {
            "total_headcount": self.total_headcount(),
            "by_department": self.headcount_by_department(),
            "by_status": self.headcount_by_status(),
            "by_gender": self.gender_breakdown(),
            "hiring_by_year": self.hiring_by_year(),
            "hiring_by_month": self.hiring_by_month(),
            "average_tenure_years": self.average_tenure_years(),
            "tenure_distribution": self.tenure_distribution(),
        }

    def insight_snapshot(self) -> Dict[str, Any]:
        """
        History-backed analytics snapshot for the Insights dashboard.
        """
        base = self.full_snapshot()
        base["fastest_growing_department"] = self.fastest_growing_department()
        base["largest_engineering_hub"] = self.largest_engineering_hub()
        base["understaffed_departments"] = self.understaffed_departments()
        base["hiring_forecast"] = self.hiring_forecast()
        return base