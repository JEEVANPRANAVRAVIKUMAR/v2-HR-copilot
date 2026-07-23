-- Migration 0002: Add updated_at column to employees table
-- Bug A: EmployeeRepository.update() writes updated_at but the column was missing

ALTER TABLE employees ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

-- Set initial updated_at for existing rows
UPDATE employees SET updated_at = created_at WHERE updated_at IS NULL;