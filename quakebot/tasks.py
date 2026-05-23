"""Task completion and scoring utilities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreBreakdown:
    survivor_detected: int = 0
    survivor_freed: int = 0
    primary_surveys: int = 0
    pulse_checks: int = 0
    breathing_checks: int = 0
    bleeding_checks: int = 0
    directly_assessed: int = 0
    stabilised: int = 0
    evacuated: int = 0
    all_accounted: int = 0
    all_three_evacuated_bonus: int = 0
    specialised_extraction: int = 0
    triage_priority: int = 0
    priority_bonus: int = 0
    rescue_notified: int = 0
    final_report_submitted: int = 0
    hazards_reported: int = 0
    random_hazard_response: int = 0
    stabilised_after_worsening: int = 0
    alternate_route: int = 0
    ignored_critical_deterioration: int = 0
    blocked_connection_attempts: int = 0
    unsafe_attempts: int = 0
    invalid_actions: int = 0
    step_cost: int = 0

    @property
    def total(self) -> int:
        return sum(self.__dict__.values())


def score_environment(env: object) -> ScoreBreakdown:
    survivors = list(getattr(env, "survivors").values())
    detected = 20 * sum(1 for s in survivors if s.discovered)
    freed = 20 * sum(1 for s in survivors if s.discovered and not s.trapped)
    primary = 15 * sum(1 for s in survivors if "perform_primary_survey" in s.checks_completed)
    pulse = 15 * sum(1 for s in survivors if getattr(s, "pulse_checked", False) or "check_pulse" in s.checks_completed)
    breathing = 15 * sum(1 for s in survivors if getattr(s, "breathing_checked", False) or "check_breathing" in s.checks_completed)
    bleeding = 15 * sum(1 for s in survivors if getattr(s, "bleeding_checked", False) or "check_bleeding" in s.checks_completed)
    directly_assessed = 20 * sum(1 for s in survivors if getattr(s, "directly_assessed", False))
    stabilised = 15 * sum(1 for s in survivors if s.stabilised)
    evacuated = 30 * sum(1 for s in survivors if s.evacuated)
    triage = 20 * len(getattr(env, "triage_tags"))
    priority_bonus = 20 if _high_before_lower(env) else 0
    rescue_notified = 20 if getattr(env, "rescue_notified") else 0
    final_report = 15 if getattr(env, "report_submitted") else 0
    hazards = 10 if getattr(env, "hazards_reported_in_final_report") else 0
    random_response = 10 * len(getattr(env, "responded_to_random_hazards", set()))
    stabilised_after = 15 * len(getattr(env, "stabilised_after_worsening", set()))
    alternate_route = 10 * int(getattr(env, "alternate_route_uses", 0))
    ignored = -20 * int(getattr(env, "critical_deterioration_ignored", 0))
    blocked_connection_attempts = -10 * int(getattr(env, "blocked_connection_attempts", 0))
    all_accounted = 20 if all(getattr(s, "accounted_for")() for s in survivors) else 0
    all_three_evacuated = 30 if len(survivors) >= 3 and all(s.evacuated for s in survivors) else 0
    specialised = 20 * sum(1 for s in survivors if getattr(s, "extraction_requested", False) and getattr(s, "inaccessible_confirmed", False))
    unsafe = -10 * int(getattr(env, "unsafe_attempts"))
    invalid = -5 * int(getattr(env, "invalid_actions"))
    step_cost = -1 * int(getattr(env, "step_count"))
    return ScoreBreakdown(
        survivor_detected=detected,
        survivor_freed=freed,
        primary_surveys=primary,
        pulse_checks=pulse,
        breathing_checks=breathing,
        bleeding_checks=bleeding,
        directly_assessed=directly_assessed,
        stabilised=stabilised,
        evacuated=evacuated,
        all_accounted=all_accounted,
        all_three_evacuated_bonus=all_three_evacuated,
        specialised_extraction=specialised,
        triage_priority=triage,
        priority_bonus=priority_bonus,
        rescue_notified=rescue_notified,
        final_report_submitted=final_report,
        hazards_reported=hazards,
        random_hazard_response=random_response,
        stabilised_after_worsening=stabilised_after,
        alternate_route=alternate_route,
        ignored_critical_deterioration=ignored,
        blocked_connection_attempts=blocked_connection_attempts,
        unsafe_attempts=unsafe,
        invalid_actions=invalid,
        step_cost=step_cost,
    )


def is_success(env: object) -> bool:
    survivors = list(getattr(env, "survivors").values())
    evacuated = [s for s in survivors if s.evacuated]
    checked = all("perform_primary_survey" in s.checks_completed for s in evacuated)
    accounting = getattr(env, "_mission_accounting")()
    return bool(
        len(evacuated) >= 2
        and checked
        and accounting["mission_can_finish"]
        and getattr(env, "rescue_notified")
        and getattr(env, "location") == "Entrance"
        and getattr(env, "report_submitted")
    )


def _high_before_lower(env: object) -> bool:
    order = getattr(env, "evacuation_order")
    if len(order) < 2:
        return False
    survivors = getattr(env, "survivors")
    ranks = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    first = ranks.get(survivors[order[0]].priority, 0)
    later = [ranks.get(survivors[sid].priority, 0) for sid in order[1:]]
    return bool(later and first >= max(later))
