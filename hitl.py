import bootstrap
import sys
from typing import Dict, Any, Tuple
import memory

# Global configuration for non-interactive / automated eval runs
AUTO_APPROVE = False


def set_auto_approve(value: bool) -> None:
    global AUTO_APPROVE
    AUTO_APPROVE = value


# Tool permission levels: 'auto', 'ask', 'deny'
DEFAULT_PERMISSIONS: Dict[str, str] = {
    "get_reddit_posts": "auto",
    "search_hn": "auto",
    "search_web": "auto",
    "read_page": "auto",
    "read_file": "auto",
    "todo_write": "auto",
    "save_lead": "auto",
    "done": "auto",
    "remember": "auto",
    "recall": "auto",
    "research_lead": "auto",
    "draft_reply": "ask",
}


def check_permission(tool_name: str) -> str:
    """Return permission level for tool: 'auto', 'ask', or 'deny'."""
    return DEFAULT_PERMISSIONS.get(tool_name, "auto")


def handle_draft_approval(url: str, text: str) -> Dict[str, Any]:
    """
    Handles human-in-the-loop review for draft_reply:
    [a]pprove: save draft
    [e]dit: save edited version and store style feedback in memory
    [r]eject: provide reason back to model
    """
    if AUTO_APPROVE:
        memory.save_lead(url=url, score=1.0, reason="Auto-approved in eval mode", status="approved", draft=text)
        return {"status": "approved", "message": f"Draft automatically approved for {url}."}

    print("\n" + "=" * 60)
    print(" [HUMAN IN THE LOOP APPROVAL REQUIRED]")
    print(f" Target URL: {url}")
    print(" Proposed Draft Reply:")
    print("-" * 60)
    print(text.strip())
    print("-" * 60)
    print(" Choices:")
    print("   [a]pprove : Save draft as approved")
    print("   [e]dit    : Enter edited version & record style feedback")
    print("   [r]eject  : Reject draft with feedback to model")
    print("=" * 60)

    while True:
        try:
            choice = input("Your decision [a/e/r]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nInterrupt received during approval. Saving as pending.")
            return {"status": "pending", "message": "Approval deferred."}

        if choice in ("a", "approve"):
            memory.update_lead_status(url=url, status="approved", draft=text)
            print(f"[HITL]: Draft approved and stored for {url}.")
            return {
                "status": "approved",
                "message": f"Draft approved and saved for {url}. Ready for human posting.",
            }

        elif choice in ("e", "edit"):
            print("Enter your edited reply below (press Enter, then type EOF or enter on empty line to finish):")
            try:
                edited_text = input("Edited text: ").strip()
            except Exception:
                edited_text = text

            memory.update_lead_status(url=url, status="approved", draft=edited_text)
            feedback_note = (
                f"For lead {url}, user edited draft. "
                f"Original draft: '{text[:120]}...' -> User edited to: '{edited_text[:120]}...'"
            )
            memory.remember(feedback_note, category="style_feedback")
            print(f"[HITL]: Edited draft saved. Recorded style feedback to memory.")
            return {
                "status": "approved_with_edits",
                "message": f"User edited draft and approved. Feedback saved: {feedback_note}",
                "final_draft": edited_text,
            }

        elif choice in ("r", "reject"):
            try:
                reason = input("Enter reason for rejection: ").strip()
            except Exception:
                reason = "Not a good fit."
            if not reason:
                reason = "Draft rejected by user without specific feedback."

            memory.update_lead_status(url=url, status="rejected")
            feedback_note = f"Draft rejected for {url}. Reason: {reason}"
            memory.remember(feedback_note, category="rejection_feedback")
            print(f"[HITL]: Draft rejected. Feedback sent back to model.")
            return {
                "status": "rejected",
                "is_error": True,
                "rejection_reason": reason,
                "instruction": f"The draft was rejected: '{reason}'. Please adjust your approach or skip this lead.",
            }
        else:
            print("Invalid choice. Please enter 'a', 'e', or 'r'.")
