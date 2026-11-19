#!/usr/bin/env python3
"""CLI utility for Siraugga course automation and active learner protection.

Usage:
    python3 scripts/automate_courses.py --status
    python3 scripts/automate_courses.py --audit [--dry-run]
    python3 scripts/automate_courses.py --from-cyberbrief [--min-score 15] [--max 2]
    python3 scripts/automate_courses.py --full-pipeline [--dry-run]
"""
import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core import course_automation as auto


def main():
    parser = argparse.ArgumentParser(description="Siraugga Course Automation & Active Learner Protection")
    parser.add_argument("--status", action="store_true", help="List active learners across all courses")
    parser.add_argument("--audit", action="store_true", help="Audit all catalog courses and sync cross-references")
    parser.add_argument("--from-cyberbrief", action="store_true", help="Generate courses from CyberBrief threat manifest")
    parser.add_argument("--full-pipeline", action="store_true", help="Run full non-destructive course automation pipeline")
    parser.add_argument("--min-score", type=int, default=15, help="Minimum story threat score for course generation (default: 15)")
    parser.add_argument("--max", type=int, default=2, help="Maximum new courses to generate per run (default: 2)")
    parser.add_argument("--dry-run", action="store_true", help="Inspect what would change without modifying files")
    args = parser.parse_args()

    if args.status:
        learners = auto.find_active_learners(repo_root=REPO_ROOT)
        active = [L for L in learners if L.get("is_active")]
        print(f"=== Active Learners Report ({len(active)} active / {len(learners)} total) ===")
        for L in learners:
            flag = "[ACTIVE]" if L["is_active"] else "[INACTIVE/DONE]"
            print(f"  {flag} Course: {L['course_id']} | Learner: {L['learner_name']} ({L['learner_id']}) | Step: {L['current_step_index']} | Completed: {L['completed_count']}")
        return

    if args.audit:
        print(f"=== Auditing Catalog Courses (dry_run={args.dry_run}) ===")
        res = auto.audit_and_sync_all_courses(dry_run=args.dry_run, repo_root=REPO_ROOT)
        print(f"Audited {res['total_courses']} courses. Updated: {res['updated']}.")
        for c in res["courses"]:
            status = "UPDATED" if c.get("updated") else ("PASS" if c.get("passed") else "FAIL")
            print(f"  [{status}] {c['course_id']} (Score: {c.get('score')})")
        return

    if args.from_cyberbrief:
        print(f"=== Generating Courses from CyberBrief Manifest (min_score={args.min_score}, max={args.max}) ===")
        res = auto.process_cyberbrief_digest(min_score=args.min_score, max_new_courses=args.max, save=not args.dry_run, repo_root=REPO_ROOT)
        print(f"Processed {res.get('processed', 0)} stories. Generated: {res.get('generated', 0)} courses.")
        for item in res.get("created_courses", []):
            print(f"  [CREATED] Course: {item['course_id']} (Score: {item.get('score')}) -> {item.get('url')}")
        return

    if args.full_pipeline or len(sys.argv) == 1:
        print(f"=== Running Full Course Automation Pipeline (dry_run={args.dry_run}) ===")
        res = auto.run_full_course_automation_pipeline(dry_run=args.dry_run, repo_root=REPO_ROOT)
        print(json.dumps(res, indent=2))
        return


if __name__ == "__main__":
    main()
