"""The first-login setup wizard.

The wizard is a pure function of (state, answers, F106 client) so that skip,
logout, reboot and stale-state behaviour can be exercised without a terminal.
Rendering is a list of lines; a TTY front end is a separate concern and is not
in this packet.

Ordering invariants the driver enforces:

* core provisioning is never waited on — the wizard refuses to start rather
  than blocking, if the state says core is incomplete;
* a checkpoint that is gated is marked ``blocked`` with the gate named, and the
  wizard **continues**, because an optional-model gate must not strand the
  operator on a screen that can never advance;
* skipping is always available and always resumable, and skipping the whole
  wizard still leaves a complete machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import browsers, sudoers
from .catalog import Consent, OptionalComponentCatalog, may_invoke_provider
from .f106_client import ContractViolation, F106Client, Failure, JsonResult, TextResult
from .gates import GateLedger, GateRefusal
from .licenses import build_presentation, request_receipt
from .plan import fit_view, hardware_report, plan_review
from .state import BLOCKED, SetupState


@dataclass(frozen=True)
class Answers:
    """Everything the operator decides, supplied up front for determinism."""

    sudo_passwordless: bool = False
    browser: str | None = None
    goals: tuple[str, ...] = ()
    selected_components: tuple[str, ...] = ()
    component_consents: Mapping[str, Consent] = field(default_factory=dict)
    confirm_plan: bool = False
    #: Checkpoint id at which the operator abandons the rest of setup.
    skip_from: str | None = None


@dataclass
class Transcript:
    lines: list[str] = field(default_factory=list)

    def section(self, title: str) -> None:
        self.lines.append("")
        self.lines.append(f"== {title}")

    def extend(self, lines: Sequence[str]) -> None:
        self.lines.extend(lines)

    def line(self, text: str) -> None:
        self.lines.append(text)

    def text(self) -> str:
        return "\n".join(self.lines).strip() + "\n"


class CoreIncomplete(RuntimeError):
    """Setup will not run before core provisioning has finished."""


@dataclass
class Wizard:
    state: SetupState
    ledger: GateLedger
    catalog: OptionalComponentCatalog
    client: F106Client | None = None
    sudoers_dir: Path | None = None

    # -- F106 access --------------------------------------------------------

    def _call(self, command_id: str, **kwargs: Any) -> JsonResult | TextResult | Failure | ContractViolation:
        if self.client is None:
            return ContractViolation("no F106 program directory is configured")
        try:
            return self.client.call(command_id, **kwargs)
        except ContractViolation as violation:
            return violation

    def _document(self, command_id: str, transcript: Transcript, **kwargs: Any) -> dict[str, Any] | None:
        """Fetch one data document, reporting every non-document outcome."""

        result = self._call(command_id, **kwargs)
        if isinstance(result, ContractViolation):
            transcript.line(f"  {command_id}: contract violation — {result}")
            return None
        if isinstance(result, Failure):
            transcript.line(
                f"  {command_id}: exit {result.exit_status} ({result.meaning}) — {result.diagnostic}"
            )
            return None
        if isinstance(result, TextResult):
            transcript.line(f"  {command_id}: text output, not parsed for decisions")
            return None
        for warning in result.warnings:
            transcript.line(f"  warning [{warning['code']}] {warning['message']}")
        return result.data

    # -- checkpoints --------------------------------------------------------

    def _welcome(self, transcript: Transcript) -> SetupState:
        transcript.extend(
            [
                "Your system is already installed and running. Nothing below is required.",
                "You can skip any step, close this tab, or log out; setup resumes where you left it.",
            ]
        )
        return self.state.complete("welcome")

    def _account_summary(self, transcript: Transcript) -> SetupState:
        if not self.state.account:
            detail = "the provisioned account could not be resolved from the install record"
            transcript.line(f"  {detail}; setup will not guess an account.")
            return self.state.block("account-summary", detail)
        transcript.line(f"Signed in as: {self.state.account}")
        transcript.line("Setup never displays or stores a password or its hash.")
        return self.state.complete("account-summary", f"account {self.state.account}")

    def _sudo_policy(self, transcript: Transcript, answers: Answers) -> SetupState:
        if not answers.sudo_passwordless:
            transcript.line("Administrator actions will keep asking for your password.")
            return self.state.complete("sudo-policy", "password required (default)")
        if not self.state.account:
            detail = "no resolved account to grant NOPASSWD to"
            transcript.line(f"  refused: {detail}")
            return self.state.block("sudo-policy", detail)
        try:
            dropin = sudoers.build_dropin(self.state.account)
        except sudoers.SudoersRefusal as refusal:
            transcript.line(f"  refused: {refusal}")
            return self.state.block("sudo-policy", str(refusal))
        directory = self.sudoers_dir or Path("/etc/sudoers.d")
        result, detail = sudoers.validate(dropin, directory)
        transcript.line(f"Drop-in {dropin.filename}, mode {oct(dropin.mode)}, one account only.")
        transcript.line(f"Validation: {result} — {detail}")
        if result != sudoers.VALIDATION_PASS:
            return self.state.block(
                "sudo-policy", f"drop-in validation {result}: {detail}"
            )
        return self.state.complete("sudo-policy", "passwordless sudo for one account")

    def _hardware_report(self, transcript: Transcript) -> SetupState:
        document = self._document("hardware.inventory", transcript)
        if document is None:
            return self.state.block("hardware-report", "no usable hardware inventory was returned")
        report = hardware_report(document)
        transcript.extend(report.render())
        if not report.usable:
            return self.state.block("hardware-report", "inventory failed consumer admission")
        return self.state.complete("hardware-report")

    def _goals_and_fit(self, transcript: Transcript, answers: Answers) -> SetupState:
        if not answers.goals:
            transcript.line("No optional capabilities were requested.")
            return self.state.skip("goals-and-fit", "no goals selected")
        blocked_reasons: list[str] = []
        for goal in answers.goals:
            command_id = f"sizer.recommend.{goal}"
            transcript.line(f"Goal: {goal}")
            document = self._document(command_id, transcript)
            if document is None:
                blocked_reasons.append(f"{goal}: no usable fit result")
                continue
            view = fit_view(document)
            transcript.extend(f"  {line}" for line in view.render())
            presentable = view.presentable_recommendation(self.ledger)
            if presentable is None:
                transcript.line(f"  Recommended: {document.get('profile_id')}")
            elif isinstance(presentable, GateRefusal):
                transcript.extend(f"  {line}" for line in presentable.render())
                blocked_reasons.append(f"{goal}: {presentable.gates[0].gate_id}")
            else:
                transcript.line(f"  No recommendation: {presentable}")
                blocked_reasons.append(f"{goal}: {presentable}")
        if blocked_reasons:
            return self.state.block("goals-and-fit", "; ".join(blocked_reasons))
        return self.state.complete("goals-and-fit")

    def _optional_components(self, transcript: Transcript, answers: Answers) -> SetupState:
        transcript.extend(self.catalog.render())
        if self.catalog.empty:
            return self.state.complete("optional-components", "empty catalog; nothing offered")

        catalog = self.catalog
        for offer_id in answers.selected_components:
            try:
                offer = catalog.get(offer_id)
            except KeyError:
                transcript.line(f"  {offer_id}: no such record; nothing was selected")
                continue
            offer = offer.select().with_consent(
                answers.component_consents.get(offer_id, Consent())
            )
            catalog = catalog.replace(offer)
        self.catalog = catalog

        for offer in catalog.selected():
            outcome = may_invoke_provider(offer, self.ledger)
            if outcome is None:
                transcript.line(f"  {offer.offer_id}: provider {offer.provider} may be invoked")
            elif isinstance(outcome, GateRefusal):
                transcript.extend(f"  {line}" for line in outcome.render())
            else:
                transcript.line(f"  {offer.offer_id}: not installed — {outcome}")

        selected = len(catalog.selected())
        if selected == 0:
            return self.state.complete(
                "optional-components", f"0/{catalog.population} offers selected"
            )
        return self.state.block(
            "optional-components",
            f"{selected}/{catalog.population} selected; provider invocation is gated",
        )

    def _default_browser(self, transcript: Transcript, answers: Answers) -> SetupState:
        for candidate in browsers.offer():
            marker = "installed" if candidate.installed else "installed on request"
            transcript.line(
                f"  {candidate.browser_id} ({candidate.label}) — Debian {candidate.component}, {marker}"
            )
        try:
            chosen, surfaces = browsers.resolve(answers.browser)
        except browsers.BrowserRefusal as refusal:
            transcript.line(f"  refused: {refusal}")
            return self.state.block("default-browser", str(refusal))
        if not surfaces:
            transcript.line(
                f"Skipped. {chosen} remains the working handler; no association was rewritten."
            )
            return self.state.skip("default-browser", f"left at shipped default {chosen}")
        transcript.line(f"Default browser: {chosen}")
        for surface in surfaces:
            transcript.line(f"  would write {surface}")
        return self.state.complete("default-browser", f"default {chosen}")

    def _plan_review(self, transcript: Transcript, answers: Answers) -> SetupState:
        document = self._document("sizer.plan.local-ai-balanced", transcript)
        if document is None:
            return self.state.block("plan-review", "no usable plan was returned")
        review = plan_review(document)
        transcript.extend(review.render())

        presentation = build_presentation(document.get("items", []), [])
        if presentation.decisions:
            transcript.line("Licences requiring a decision:")
            transcript.extend(f"  {line}" for line in presentation.render())
        else:
            transcript.line("No licence decisions are pending: the plan selects no items.")
        receipt_refusal = request_receipt("plan", self.ledger)
        transcript.extend(f"  {line}" for line in receipt_refusal.render())

        outcome = review.may_execute(self.ledger, confirmed=answers.confirm_plan)
        if outcome is None:
            transcript.line("The plan may be executed.")
            return self.state.complete("plan-review")
        if isinstance(outcome, GateRefusal):
            transcript.extend(outcome.render())
            return self.state.block("plan-review", outcome.gates[0].gate_id)
        transcript.line(f"Not executed: {outcome}")
        return self.state.block("plan-review", outcome)

    # -- driver -------------------------------------------------------------

    def run(self, answers: Answers) -> tuple[SetupState, str]:
        if not self.state.core_complete:
            raise CoreIncomplete(
                "core provisioning has not finished; setup must never be what it waits on"
            )

        transcript = Transcript()
        handlers = {
            "welcome": lambda t: self._welcome(t),
            "account-summary": lambda t: self._account_summary(t),
            "sudo-policy": lambda t: self._sudo_policy(t, answers),
            "hardware-report": lambda t: self._hardware_report(t),
            "goals-and-fit": lambda t: self._goals_and_fit(t, answers),
            "optional-components": lambda t: self._optional_components(t, answers),
            "default-browser": lambda t: self._default_browser(t, answers),
            "plan-review": lambda t: self._plan_review(t, answers),
        }

        while True:
            checkpoint_id = self.state.resume_at()
            if checkpoint_id is None:
                break
            if answers.skip_from is not None and checkpoint_id == answers.skip_from:
                transcript.section("Skipped by the operator")
                transcript.line(
                    "The remaining steps were skipped. The system is complete and usable."
                )
                self.state = self.state.skip_all_remaining("skipped by the operator")
                break
            transcript.section(self.state.get(checkpoint_id).title)
            self.state = handlers[checkpoint_id](transcript)

        counts = self.state.counts()
        transcript.section("Setup summary")
        transcript.line(
            f"Checkpoints: {counts['complete']} complete, {counts['skipped']} skipped, "
            f"{counts[BLOCKED]} blocked, {counts['pending']} pending, "
            f"of {len(self.state.checkpoints)} total."
        )
        transcript.line(
            "Core system: complete and unaffected by anything above."
            if self.state.core_complete
            else "Core system: incomplete."
        )
        for checkpoint in self.state.checkpoints:
            if checkpoint.status == BLOCKED:
                transcript.line(f"  blocked: {checkpoint.checkpoint_id} — {checkpoint.detail}")
        return self.state, transcript.text()
