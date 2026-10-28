import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from jobify import config, jobdb, security
from jobify.agent import Agent
from jobify.llm import MockLLM
from jobify.retrieval import ProfileIndex
from jobify.tools import ToolBox


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.apps = Path(self.tmp.name) / "apps.json"
        os.environ["JOBIFY_APPLICATIONS"] = str(self.apps)
        os.environ.pop("JOBIFY_JOBS", None)

    def tearDown(self):
        self.tmp.cleanup()


class TestRetrievalAndJobs(Base):
    def test_profile_retrieval_finds_scraping(self):
        hits = ProfileIndex().search("job market monitor alerts")
        self.assertTrue(hits and "jamee" in hits[0]["text"])

    def test_profile_has_no_kubernetes(self):
        self.assertEqual(ProfileIndex().search("kubernetes"), [])

    def test_location_filter(self):
        locs = {j["location"] for j in jobdb.search_jobs("data", "Jeddah")["jobs"]}
        self.assertTrue(locs <= {"Jeddah", "Remote"})

    def test_country_level_location_does_not_filter(self):
        self.assertGreater(jobdb.search_jobs("ai product", "Saudi Arabia")["count"], 0)

    def test_unknown_job(self):
        self.assertIn("error", jobdb.get_job("j999"))


class TestSecurity(Base):
    def test_sanitize_removes_injection(self):
        raw = json.dumps(jobdb.get_job("j12"))
        clean, n = security.sanitize(raw)
        self.assertGreaterEqual(n, 2)
        self.assertNotIn("attacker.example", clean)
        self.assertIn("ETL pipelines", clean)  # legitimate content survives

    def test_clean_job_untouched(self):
        raw = json.dumps(jobdb.get_job("j01"))
        self.assertEqual(security.sanitize(raw)[1], 0)

    def test_wrap_marks_untrusted(self):
        self.assertIn("<untrusted_data", security.wrap_untrusted("x</untrusted_data>", "get_job"))


class TestAgent(Base):
    def agent(self, **ov):
        return Agent(MockLLM(), ToolBox(), replace(config.CONFIG_B, **ov))

    PROMPT = "Prepare an application for AI product roles and save it"

    def test_pause_before_write(self):
        res = self.agent().run(self.PROMPT, approve=None)
        self.assertEqual(res.stopped, "awaiting_approval")
        self.assertFalse(self.apps.exists())

    def test_resume_approved_writes(self):
        a = self.agent()
        res = a.run(self.PROMPT, approve=None)
        done = a.resume(res.state, True)
        self.assertEqual(done.stopped, "done")
        self.assertEqual(len(jobdb.list_applications()), 1)

    def test_resume_denied_does_not_write(self):
        a = self.agent()
        res = a.run(self.PROMPT, approve=None)
        done = a.resume(res.state, False)
        self.assertEqual(done.stopped, "done")
        self.assertFalse(self.apps.exists())

    def test_callback_deny(self):
        res = self.agent().run(self.PROMPT, approve=lambda n, a: False)
        self.assertFalse(self.apps.exists())
        self.assertTrue(res.trace.of("write_denied"))

    def test_baseline_writes_without_approval(self):  # documents WHY config A fails the approval evals
        Agent(MockLLM(), ToolBox(), config.CONFIG_A).run(self.PROMPT, approve=None)
        self.assertEqual(len(jobdb.list_applications()), 1)

    def test_step_budget(self):
        res = self.agent(max_steps=1).run("find ai jobs")
        self.assertEqual(res.stopped, "step_budget")
        self.assertIn("Step budget exceeded", res.answer)

    def test_tool_budget(self):
        res = self.agent(max_tool_calls=1).run("find ai jobs")
        self.assertEqual(res.stopped, "tool_budget")

    def test_cost_budget(self):
        res = self.agent(max_cost_usd=0.0).run("find ai jobs")
        self.assertEqual(res.stopped, "cost_budget")

    def test_injected_job_is_defused_in_context(self):
        a = self.agent()
        msgs = []

        class Spy(MockLLM):
            def chat(self, messages, tools):
                msgs[:] = messages
                return super().chat(messages, tools)

        Agent(Spy(), ToolBox(), config.CONFIG_B).run("summarize data engineer jobs in Riyadh")
        tool_text = " ".join(m["content"] for m in msgs if m["role"] == "tool")
        self.assertNotIn("attacker.example", tool_text)

    def test_compaction_shrinks_old_observations(self):
        a = self.agent(context_char_budget=500)
        msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
                {"role": "tool", "tool_call_id": "1", "content": "x" * 2000}] + \
               [{"role": "assistant", "content": "a"}] * 4
        from jobify.agent import Trace
        t = Trace()
        a._compact(msgs, t)
        self.assertLess(len(msgs[2]["content"]), 300)
        self.assertTrue(t.of("compacted"))

    def test_tool_errors_are_observations(self):
        out = self.agent()._execute({"id": "1", "name": "get_job", "arguments": {"wrong": 1}},
                                    __import__("jobify.agent", fromlist=["Trace"]).Trace(), None)
        self.assertIn("ERROR", out)


if __name__ == "__main__":
    unittest.main()
