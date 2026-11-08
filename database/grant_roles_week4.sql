-- Muc dich: cap quyen Admin va Employee cho tai khoan da dang ky.
-- File nay khong tao tai khoan va khong xu ly mat khau.
-- Dang ky tai khoan truoc qua API de backend tu bam mat khau.
--
-- Cach su dung:
-- 1. Thay bon username mau ben duoi bang username da dang ky.
-- 2. Mo terminal Ubuntu tai thu muc goc cua du an.
-- 3. Chay lenh:
--    docker exec -i deployment-postgres-1 sh -lc 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < database/grant_roles_week4.sql
-- 4. Kiem tra ket qua hien ra dung 2 Admin va 2 Employee.
--
-- Script se dung neu username chua ton tai, bi trung, van con gia tri mau,
-- hoac tai khoan dang co role khac Customer/Admin/Employee.
-- Tat ca thay doi duoc dat trong mot transaction va chi commit khi kiem tra hop le.

BEGIN;

CREATE TEMP TABLE week4_target_roles (
    username TEXT PRIMARY KEY,
    target_role TEXT NOT NULL CHECK (target_role IN ('Admin', 'Employee'))
) ON COMMIT DROP;

INSERT INTO week4_target_roles (username, target_role) VALUES
    ('admin1', 'Admin'),
    ('admin2', 'Admin'),
    ('emp1', 'Employee'),
    ('emp2', 'Employee');

DO $$
DECLARE
    matched_count INTEGER;
BEGIN
    IF (SELECT count(*) FROM week4_target_roles) <> 4 THEN
        RAISE EXCEPTION 'Can khai bao dung 4 username khac nhau';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM week4_target_roles
        WHERE username LIKE 'THAY_USERNAME_%'
    ) THEN
        RAISE EXCEPTION 'Hay thay tat ca username mau truoc khi chay';
    END IF;

    SELECT count(*)
    INTO matched_count
    FROM week4_target_roles AS target
    JOIN users AS account ON account.username = target.username;

    IF matched_count <> 4 THEN
        RAISE EXCEPTION 'Moi username phai khop dung mot tai khoan da dang ky';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM week4_target_roles AS target
        JOIN users AS account ON account.username = target.username
        WHERE (target.target_role = 'Admin'
               AND account.role NOT IN ('Customer', 'Admin', 'ADMIN'))
           OR (target.target_role = 'Employee'
               AND account.role NOT IN ('Customer', 'Employee', 'OPERATOR'))
    ) THEN
        RAISE EXCEPTION 'Co tai khoan dang co role khong phu hop; khong cap quyen';
    END IF;
END
$$;

UPDATE users AS account
SET role = target.target_role
FROM week4_target_roles AS target
WHERE account.username = target.username;

SELECT account.username, account.role
FROM users AS account
JOIN week4_target_roles AS target ON target.username = account.username
ORDER BY target.target_role, account.username;

COMMIT;
