"""Provider-assisted review of deterministic possible matches."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from ..llm.base import LLMProvider
from ..models import MatchStatus
from .state import GraphState
_PROMPT=(Path(__file__).parent/"prompts"/"resolver_v1.txt").read_text(encoding="utf-8")
def _invoice_data(invoice: Any)->dict[str,str]:
 return {"row_id":invoice.row_id,"supplier_gstin":invoice.supplier_gstin,"supplier_name":invoice.supplier_name,"invoice_number":invoice.invoice_number_raw,"invoice_date":invoice.invoice_date.isoformat(),"taxable_value":str(invoice.taxable_value),"igst":str(invoice.igst),"cgst":str(invoice.cgst),"sgst":str(invoice.sgst),"cess":str(invoice.cess),"invoice_value":str(invoice.invoice_value)}
def resolve_matches(state: GraphState, provider: LLMProvider)->GraphState:
 for result in state.get("match_results",[]):
  if result.status is not MatchStatus.POSSIBLE_MATCH or not result.books_invoice or not result.gstr2b_invoice: continue
  payload={"books_invoice":_invoice_data(result.books_invoice),"gstr2b_invoice":_invoice_data(result.gstr2b_invoice),"matcher_reason":list(result.notes)}
  response=provider.structured_completion(_PROMPT+"\nINPUT:\n"+repr(payload),output_schema={"suggestion":"string","reason":"string","human_confirmation_required":"boolean"})
  data=response.get("structured",response.get("content",{})); data=data if isinstance(data,dict) else {}
  suggestion=data.get("suggestion") or data.get("response") or "Review this candidate against the source invoices before accepting it."
  reason=data.get("reason") or (result.notes[0] if result.notes else "The matcher identified a possible match requiring review.")
  result.resolver_suggestion=str(suggestion)
  if str(reason) not in result.notes: result.notes.append(str(reason))
  result.human_confirmation_required=True
 return state
def resolver(state: GraphState, provider: LLMProvider)->GraphState: return resolve_matches(state,provider)
__all__=["resolve_matches","resolver"]
