from database.queries.employee_repository import EmployeeRepository
from models.employee import EmployeeCreate

repo = EmployeeRepository()

employee = EmployeeCreate(
    employee_no="EMP999",
    full_name="Test Employee",
)

created = repo.create(employee)

print(created)

updated = repo.update(
    "EMP999",
    {"full_name": "Updated Employee"}
)