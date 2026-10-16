"""Supplier-scoped draft generation with a deterministic safe fallback."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from ..llm.base import LLMProvider
from ..models import Invoice
from .state import GraphState
_PROMPT=(Path(__file__).parent/"prompts"/"drafter_v1.txt").read_text(encoding="utf-8")
def _fields(i: Invoice)->dict[str,str]:
 return {"row_id":i.row_id,"supplier_gstin":i.supplier_gstin,"supplier_name":i.supplier_name,"invoice_number":i.invoice_number_raw,"invoice_date":i.invoice_date.isoformat(),"taxable_value":str(i.taxable_value),"igst":str(i.igst),"cgst":str(i.cgst),"sgst":str(i.sgst),"cess":str(i.cess),"invoice_value":str(i.invoice_value)}
def _fallback(supplier:str, issues:list[tuple[str,Any]])->str:
 lines=[f"Subject: ITC reconciliation items for {supplier}","","Please review the following source-record items:"]
 for _,r in issues:
  i=r.books_invoice or r.gstr2b_invoice
  lines.append(f"- Invoice {i.invoice_number_raw} dated {i.invoice_date.isoformat()}: {r.status.value}.") if i else lines.append("- The source records require review.")
 lines.append("Please compare these items with your records and reply with any corrections or supporting records.")
 return "\n".join(lines)
def draft_supplier_messages(state:GraphState, provider:LLMProvider|None=None)->GraphState:
 grouped:dict[str,list[tuple[str,Any]]]={}
 for n,r in enumerate(state.get("match_results",[])):
  i=r.books_invoice or r.gstr2b_invoice
  if i is not None and r.status.value!="MATCHED": grouped.setdefault(i.supplier_name,[]).append((str(n),r))
 drafts=dict(state.get("drafts",{}))
 for supplier,issues in grouped.items():
  inv=[]
  for _,r in issues:
   for i in (r.books_invoice,r.gstr2b_invoice):
    if i is not None and _fields(i) not in inv: inv.append(_fields(i))
  payload={"supplier":supplier,"issues":[{"status":r.status.value,"explanation":r.explanation,"notes":r.notes} for _,r in issues],"invoices":inv}; text=""
  if provider:
   out=provider.structured_completion(_PROMPT+"\nINPUT:\n"+repr(payload),output_schema={"draft":"string"}); data=out.get("structured",out.get("content",{})); text=str(data.get("draft") or data.get("response") or "") if isinstance(data,dict) else ""
  drafts[supplier]=text if text and text!="MOCK_COMPLETION" else _fallback(supplier,issues)
 state["drafts"]=drafts; return state
def drafter(state:GraphState,provider:LLMProvider|None=None)->GraphState: return draft_supplier_messages(state,provider)
__all__=["draft_supplier_messages","drafter"]
