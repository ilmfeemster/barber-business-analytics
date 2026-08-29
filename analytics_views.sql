DROP VIEW IF EXISTS v_monthly_performance;
DROP VIEW IF EXISTS v_client_completed_visits;
DROP VIEW IF EXISTS v_analysis_appointments;

CREATE VIEW v_analysis_appointments AS
SELECT
    booking_id,
    appointment_datetime,
    date(appointment_datetime) AS appointment_date,
    substr(appointment_datetime, 1, 7) AS appointment_month,
    main_category,
    service,
    staffer,
    service_value,
    addons_value,
    revenue_net,
    discount,
    tax,
    tip_amount,
    total_revenue,
    status,
    service_length_minutes,
    client_key,
    client_match_status,
    CASE WHEN status = 'Completed' THEN 1 ELSE 0 END AS is_completed,
    CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END AS is_cancelled,
    CASE WHEN status = 'No-show' THEN 1 ELSE 0 END AS is_no_show
FROM appointments
WHERE service <> 'LEAVE A REVIEW';

CREATE VIEW v_client_completed_visits AS
WITH sequenced AS (
    SELECT
        a.booking_id,
        a.appointment_datetime,
        a.appointment_date,
        a.appointment_month,
        a.service,
        a.service_value,
        a.total_revenue,
        a.client_key,
        a.client_match_status,
        c.first_visit AS booksy_first_visit,
        ROW_NUMBER() OVER (
            PARTITION BY a.client_key
            ORDER BY a.appointment_datetime, a.booking_id
        ) AS observed_visit_number,
        MIN(a.appointment_datetime) OVER (
            PARTITION BY a.client_key
        ) AS observed_first_completed_visit
    FROM v_analysis_appointments a
    JOIN clients c
      ON c.client_key = a.client_key
    WHERE a.status = 'Completed'
      AND a.client_key IS NOT NULL
)
SELECT
    *,
    CASE WHEN observed_visit_number = 1 THEN 1 ELSE 0 END AS is_first_observed_completed_visit,
    CASE WHEN observed_visit_number > 1 THEN 1 ELSE 0 END AS is_repeat_completed_visit,
    CASE
        WHEN date(booksy_first_visit) < '2025-07-25' THEN 1
        ELSE 0
    END AS booksy_indicates_pre_reporting_client,
    CASE
        WHEN observed_visit_number = 1
         AND date(booksy_first_visit) >= '2025-07-25'
        THEN 1 ELSE 0
    END AS is_observed_new_client
FROM sequenced;

CREATE VIEW v_monthly_performance AS
WITH months AS (
    SELECT DISTINCT appointment_month AS month
    FROM v_analysis_appointments
),
appointment_metrics AS (
    SELECT
        appointment_month AS month,
        COUNT(*) AS booked_service_appointments,
        SUM(is_completed) AS completed_service_appointments,
        SUM(is_cancelled) AS cancelled_service_appointments,
        SUM(is_no_show) AS no_show_service_appointments,
        COUNT(DISTINCT CASE WHEN status = 'Completed' THEN client_key END) AS unique_completed_clients,
        SUM(CASE WHEN status = 'Completed' THEN service_length_minutes ELSE 0 END) AS completed_service_minutes,
        SUM(CASE WHEN status = 'Completed' THEN service_value ELSE 0 END) AS completed_service_value
    FROM v_analysis_appointments
    GROUP BY appointment_month
),
client_metrics AS (
    SELECT
        appointment_month AS month,
        COUNT(DISTINCT CASE WHEN is_observed_new_client = 1 THEN client_key END) AS observed_new_clients,
        COUNT(DISTINCT CASE WHEN is_repeat_completed_visit = 1 THEN client_key END) AS returning_clients
    FROM v_client_completed_visits
    GROUP BY appointment_month
)
SELECT
    m.month,
    a.booked_service_appointments,
    a.completed_service_appointments,
    a.cancelled_service_appointments,
    a.no_show_service_appointments,
    a.unique_completed_clients,
    COALESCE(c.observed_new_clients, 0) AS observed_new_clients,
    COALESCE(c.returning_clients, 0) AS returning_clients,
    ROUND(1.0 * a.completed_service_appointments / NULLIF(a.booked_service_appointments, 0), 4) AS completion_rate,
    ROUND(1.0 * a.cancelled_service_appointments / NULLIF(a.booked_service_appointments, 0), 4) AS cancellation_rate,
    ROUND(1.0 * a.no_show_service_appointments / NULLIF(a.booked_service_appointments, 0), 4) AS no_show_rate,
    a.completed_service_minutes,
    a.completed_service_value,
    CASE
        WHEN m.month < '2026-03' THEN 'pre_gbp'
        WHEN m.month = '2026-03' THEN 'gbp_creation_month'
        ELSE 'post_gbp'
    END AS intervention_period,
    CASE
        WHEN m.month = '2025-07' OR m.month = '2026-08' THEN 1
        ELSE 0
    END AS is_partial_month
FROM months m
JOIN appointment_metrics a ON a.month = m.month
LEFT JOIN client_metrics c ON c.month = m.month
ORDER BY m.month;

DROP VIEW IF EXISTS v_monthly_active_clients;
DROP VIEW IF EXISTS v_client_cohorts;
DROP VIEW IF EXISTS v_client_retention;

-- Retention is based on distinct completed service DAYS, not appointment rows.
-- This prevents two services/appointments on the same day from being counted as a return visit.
CREATE VIEW v_client_retention AS
WITH visit_days AS (
    SELECT DISTINCT client_key, appointment_date
    FROM v_client_completed_visits
),
sequenced_days AS (
    SELECT
        client_key,
        appointment_date,
        ROW_NUMBER() OVER (PARTITION BY client_key ORDER BY appointment_date) AS visit_day_number
    FROM visit_days
),
client_visits AS (
    SELECT
        client_key,
        MIN(appointment_date) AS first_completed_visit,
        MAX(appointment_date) AS latest_completed_visit,
        COUNT(*) AS completed_visit_days,
        MAX(CASE WHEN visit_day_number = 2 THEN appointment_date END) AS second_completed_visit
    FROM sequenced_days
    GROUP BY client_key
),
observation AS (
    SELECT MAX(appointment_date) AS observation_end_date
    FROM v_analysis_appointments
    WHERE status = 'Completed'
)
SELECT
    v.client_key,
    v.first_completed_visit,
    substr(v.first_completed_visit, 1, 7) AS acquisition_cohort_month,
    v.second_completed_visit,
    v.latest_completed_visit,
    v.completed_visit_days,
    CAST(julianday(v.second_completed_visit) - julianday(v.first_completed_visit) AS INTEGER) AS days_to_second_visit,
    CASE WHEN v.second_completed_visit IS NOT NULL THEN 1 ELSE 0 END AS ever_repeated_observed,
    CASE WHEN date(v.first_completed_visit, '+42 days') <= o.observation_end_date THEN 1 ELSE 0 END AS eligible_for_42d_repeat,
    CASE WHEN date(v.first_completed_visit, '+42 days') <= o.observation_end_date
          AND v.second_completed_visit IS NOT NULL
          AND julianday(v.second_completed_visit) - julianday(v.first_completed_visit) <= 42
         THEN 1 ELSE 0 END AS repeated_within_42d,
    CASE WHEN date(v.first_completed_visit, '+90 days') <= o.observation_end_date THEN 1 ELSE 0 END AS eligible_for_90d_repeat,
    CASE WHEN date(v.first_completed_visit, '+90 days') <= o.observation_end_date
          AND v.second_completed_visit IS NOT NULL
          AND julianday(v.second_completed_visit) - julianday(v.first_completed_visit) <= 90
         THEN 1 ELSE 0 END AS repeated_within_90d,
    o.observation_end_date
FROM client_visits v
CROSS JOIN observation o;

CREATE VIEW v_client_cohorts AS
SELECT
    acquisition_cohort_month AS cohort_month,
    COUNT(*) AS acquired_clients,
    SUM(ever_repeated_observed) AS clients_ever_repeated_observed,
    ROUND(1.0 * SUM(ever_repeated_observed) / NULLIF(COUNT(*), 0), 4) AS observed_repeat_rate,
    SUM(eligible_for_42d_repeat) AS clients_eligible_42d,
    SUM(CASE WHEN eligible_for_42d_repeat = 1 THEN repeated_within_42d ELSE 0 END) AS clients_repeated_42d,
    ROUND(1.0 * SUM(CASE WHEN eligible_for_42d_repeat = 1 THEN repeated_within_42d ELSE 0 END)
          / NULLIF(SUM(eligible_for_42d_repeat), 0), 4) AS repeat_rate_42d,
    SUM(eligible_for_90d_repeat) AS clients_eligible_90d,
    SUM(CASE WHEN eligible_for_90d_repeat = 1 THEN repeated_within_90d ELSE 0 END) AS clients_repeated_90d,
    ROUND(1.0 * SUM(CASE WHEN eligible_for_90d_repeat = 1 THEN repeated_within_90d ELSE 0 END)
          / NULLIF(SUM(eligible_for_90d_repeat), 0), 4) AS repeat_rate_90d,
    ROUND(AVG(CASE WHEN second_completed_visit IS NOT NULL THEN days_to_second_visit END), 1) AS avg_days_to_second_visit,
    CASE WHEN acquisition_cohort_month < '2026-03' THEN 'pre_gbp'
         WHEN acquisition_cohort_month = '2026-03' THEN 'gbp_creation_month'
         ELSE 'post_gbp' END AS intervention_period,
    CASE WHEN acquisition_cohort_month IN ('2025-07', '2026-08') THEN 1 ELSE 0 END AS is_partial_month
FROM v_client_retention
GROUP BY acquisition_cohort_month
ORDER BY acquisition_cohort_month;

CREATE VIEW v_monthly_active_clients AS
WITH RECURSIVE month_ends(month, month_end) AS (
    SELECT substr(MIN(appointment_date), 1, 7),
           date(MIN(appointment_date), 'start of month', '+1 month', '-1 day')
    FROM v_analysis_appointments
    UNION ALL
    SELECT strftime('%Y-%m', date(month_end, '+1 day')),
           date(month_end, '+1 day', 'start of month', '+1 month', '-1 day')
    FROM month_ends
    WHERE month_end < (SELECT MAX(appointment_date) FROM v_analysis_appointments)
),
completed AS (
    SELECT DISTINCT client_key, appointment_date
    FROM v_analysis_appointments
    WHERE status = 'Completed' AND client_key IS NOT NULL
)
SELECT
    m.month,
    m.month_end,
    COUNT(DISTINCT CASE WHEN c.appointment_date BETWEEN date(m.month_end, '-41 days') AND m.month_end THEN c.client_key END) AS active_clients_42d,
    COUNT(DISTINCT CASE WHEN c.appointment_date BETWEEN date(m.month_end, '-89 days') AND m.month_end THEN c.client_key END) AS active_clients_90d,
    CASE WHEN m.month < '2026-03' THEN 'pre_gbp'
         WHEN m.month = '2026-03' THEN 'gbp_creation_month'
         ELSE 'post_gbp' END AS intervention_period,
    CASE WHEN m.month IN ('2025-07', '2026-08') THEN 1 ELSE 0 END AS is_partial_month
FROM month_ends m
LEFT JOIN completed c ON c.appointment_date <= m.month_end
GROUP BY m.month, m.month_end
ORDER BY m.month;

DROP VIEW IF EXISTS v_repeat_cadence_summary;
DROP VIEW IF EXISTS v_client_visit_intervals;
DROP VIEW IF EXISTS v_service_monthly;

CREATE VIEW v_client_visit_intervals AS
WITH visit_days AS (
    SELECT DISTINCT client_key, appointment_date
    FROM v_analysis_appointments
    WHERE status = 'Completed' AND client_key IS NOT NULL
), sequenced AS (
    SELECT client_key, appointment_date,
           LAG(appointment_date) OVER (PARTITION BY client_key ORDER BY appointment_date) AS prior_visit_date
    FROM visit_days
)
SELECT client_key, prior_visit_date, appointment_date AS return_visit_date,
       CAST(julianday(appointment_date) - julianday(prior_visit_date) AS INTEGER) AS days_between_visits
FROM sequenced
WHERE prior_visit_date IS NOT NULL;

CREATE VIEW v_repeat_cadence_summary AS
SELECT CASE
        WHEN days_between_visits <= 14 THEN '01_0_14_days'
        WHEN days_between_visits <= 21 THEN '02_15_21_days'
        WHEN days_between_visits <= 28 THEN '03_22_28_days'
        WHEN days_between_visits <= 35 THEN '04_29_35_days'
        WHEN days_between_visits <= 42 THEN '05_36_42_days'
        WHEN days_between_visits <= 60 THEN '06_43_60_days'
        WHEN days_between_visits <= 90 THEN '07_61_90_days'
        ELSE '08_91_plus_days' END AS cadence_band,
       COUNT(*) AS return_intervals,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_return_intervals
FROM v_client_visit_intervals
GROUP BY cadence_band
ORDER BY cadence_band;

CREATE VIEW v_service_monthly AS
SELECT substr(appointment_date, 1, 7) AS month, service,
       COUNT(*) AS booked_appointments,
       SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed_appointments,
       ROUND(AVG(CASE WHEN status = 'Completed' THEN service_value END), 2) AS avg_completed_service_value,
       ROUND(AVG(CASE WHEN status = 'Completed' THEN service_length_minutes END), 1) AS avg_completed_service_minutes,
       MIN(CASE WHEN status = 'Completed' THEN appointment_date END) AS first_completed_date_in_month,
       MAX(CASE WHEN status = 'Completed' THEN appointment_date END) AS last_completed_date_in_month
FROM v_analysis_appointments
GROUP BY substr(appointment_date, 1, 7), service
ORDER BY month, completed_appointments DESC, service;
