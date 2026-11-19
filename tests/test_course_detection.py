"""A learner asking for a course must get the course (or the course list), not a code inspection by the agent."""
import unittest

from core import response_cards as rc


class CourseRequestDetection(unittest.TestCase):
    def test_natural_requests_open_the_named_course(self):
        for prompt, cid in [
            ("can you render the linux course", "linux_essentials_step_by_step"),
            ("give me the linux labs", "linux_essentials_step_by_step"),
            ("open linux essentials", "linux_essentials_step_by_step"),
            ("show the course about linux", "linux_essentials_step_by_step"),
            ("/course linux", "linux_essentials_step_by_step"),
            ("start networking revision", "networking_revision"),
            ("lets try th elynex fundamentals course", "linux_essentials_step_by_step"),   # typos + a word shared by courses
            ("lets try the linix course", "linux_essentials_step_by_step"),
        ]:
            self.assertEqual(rc.detect_course_request(prompt), "course:" + cid, prompt)

    def test_unnamed_requests_show_the_course_list_not_the_agent(self):
        for prompt in ["give me the course", "render me the course so I can test it", "I want to check the course",
                       "run the course", "lets do the course"]:
            self.assertEqual(rc.detect_course_request(prompt), "course_help", prompt)

    def test_change_requests_and_questions_still_go_to_the_agent(self):
        for prompt in ["fix the course page", "why does the course not load", "how does the course work",
                       "change the course colours", "explain the linux course", "add a lab to the course"]:
            self.assertIsNone(rc.detect_course_request(prompt), prompt)


class CourseCatalog(unittest.TestCase):
    def test_every_course_on_disk_is_in_the_catalog_automatically(self):
        in_catalog = {c["id"] for _, cs in rc.course_catalog() for c in cs}
        self.assertEqual(in_catalog, {c["id"] for c in rc.list_courses()})

    def test_category_comes_from_the_course_itself_or_its_name_or_falls_back(self):
        self.assertEqual(rc.course_category({"id": "x", "title": "Anything", "category": "Databases"}), "Databases")
        self.assertEqual(rc.course_category({"id": "kubernetes_basics", "title": "Kubernetes Basics"}), "Cloud & Infrastructure")
        self.assertEqual(rc.course_category({"id": "cyberbrief_new_flaw", "title": "Threat Defense: New flaw"}), "Threat briefings")
        self.assertEqual(rc.course_category({"id": "cooking", "title": "Cooking"}), "Other courses")

    def test_help_menu_lists_the_catalog(self):
        titles = [g["title"] for g in rc.build_card("menu")["button_groups"]]
        for cat, _ in rc.course_catalog():
            self.assertTrue(any(cat in t for t in titles), cat)


if __name__ == "__main__":
    unittest.main()
