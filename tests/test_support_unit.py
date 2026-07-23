from support.ranking import effectiveness,total
from support.security import anonymize,anonymize_with_report,client_reference
from support.workflow import interpret_locally,validate_feedback
from support.worker import enrich_description,json_safe
import support.graph as support_graph
import support.learning as support_learning
import support.chat as support_chat
from iodo_rag.chunking import detect_document_type,split_into_chunks
from iodo_rag.parsers import parse_docx
from docx import Document

def test_ranking_weights(): assert total(1,1,1)==1
def test_effectiveness_has_prior(): assert effectiveness(1,0,0)<1
def test_anonymization():
    value=anonymize("Kontakt jan@example.com, tel. 501 502 503")
    assert "jan@example.com" not in value and "501 502 503" not in value
def test_external_privacy_redacts_pesel_and_credentials():
    value,categories=anonymize_with_report("Pacjent Jan Kowalski PESEL 44051401458, hasło: Tajne123, IP 10.2.3.4")
    assert "44051401458" not in value and "Jan Kowalski" not in value and "Tajne123" not in value and "10.2.3.4" not in value
    assert {"pesel_or_id","person","credential","ip"}.issubset(set(categories))
def test_client_reference_is_stable_pseudonym():
    assert client_reference(12,"secret")==client_reference(12,"secret")
    assert client_reference(12,"secret")!=client_reference(13,"secret")
def test_hybrid_llm_prefers_external(monkeypatch):
    monkeypatch.setattr(support_graph,"external_llm_answer",lambda prompt,runtime:"API")
    monkeypatch.setattr(support_graph,"local_llm_answer",lambda prompt,runtime:(_ for _ in ()).throw(AssertionError("fallback nie powinien ruszyć")))
    assert support_graph.hybrid_llm_answer("prompt",{"external_llm_enabled":1})==("API","external_api","")
def test_hybrid_llm_falls_back_to_ollama(monkeypatch):
    monkeypatch.setattr(support_graph,"external_llm_answer",lambda prompt,runtime:(_ for _ in ()).throw(TimeoutError("timeout")))
    monkeypatch.setattr(support_graph,"local_llm_answer",lambda prompt,runtime:"LOCAL")
    answer,provider,error=support_graph.hybrid_llm_answer("prompt",{"external_llm_enabled":1})
    assert answer=="LOCAL" and provider=="ollama_fallback" and "timeout" in error
def test_knowledge_curator_reuses_existing_solution(monkeypatch):
    monkeypatch.setattr(support_learning,"application_settings",lambda cur:{"external_llm_enabled":1})
    monkeypatch.setattr(support_learning,"hybrid_llm_answer",lambda prompt,runtime:(
        '{"action":"supplement","problem_id":7,"solution_id":9,"confidence":0.91,"reason":"ta sama przyczyna"}',
        "external_api",""))
    candidates=[{"problem_id":7,"problem_title":"Błąd usługi","problem_description":"Brak połączenia",
                 "solution_id":9,"solution_title":"Restart","solution_summary":"Uruchom usługę","solution_client_id":None}]
    decision,provider,error=support_learning.curate_knowledge(None,"Brak usługi","Restart usługi","Naprawa",candidates,"K-test")
    assert decision["action"]=="supplement" and decision["solution_id"]==9 and provider=="external_api" and not error
def test_knowledge_curator_rejects_unknown_ids(monkeypatch):
    monkeypatch.setattr(support_learning,"application_settings",lambda cur:{})
    monkeypatch.setattr(support_learning,"hybrid_llm_answer",lambda prompt,runtime:(
        '{"action":"duplicate","problem_id":999,"solution_id":888}',"external_api",""))
    try:
        support_learning.curate_knowledge(None,"Opis","Rozwiązanie","Tytuł",[],"K-test")
        assert False,"oczekiwano odrzucenia obcego ID"
    except ValueError:
        pass
def test_instruction_chunking_keeps_procedures_separate():
    text="# Restart usługi\n\n1. Otwórz panel usług.\n\n2. Uruchom usługę i sprawdź log.\n\n# Konfiguracja certyfikatu\n\n1. Otwórz magazyn certyfikatów.\n\n2. Zaimportuj certyfikat."
    assert detect_document_type(text)=="instruction"
    chunks=split_into_chunks(text,target_chars=100,overlap_chars=220)
    assert len(chunks)>=2
    assert all(not ("Restart usługi" in chunk["text"] and "Konfiguracja certyfikatu" in chunk["text"]) for chunk in chunks)
    assert any("Restart usługi" in chunk["text"] and "Uruchom usługę" in chunk["text"] for chunk in chunks)
def test_docx_parser_preserves_heading_style(tmp_path):
    path=tmp_path/"instruction.docx"; document=Document()
    document.add_heading("Procedura aktualizacji",level=1)
    document.add_paragraph("1. Wykonaj kopię zapasową.")
    document.save(path)
    text,_=parse_docx(path)
    assert "# Procedura aktualizacji" in text
def test_support_prompt_is_technical_not_legal():
    prompt=support_graph.build_technical_support_prompt({
        "client_ref":"K-test","effective_description":"ERR-1234 podczas zapisu w module ASW",
        "sources":[{"kind":"documentation","id":"1","chunk_text":"Sprawdź usługę ZSIMED i jej log."}],
    })
    assert "SŁOWA KLUCZOWE" in prompt and "ZALECANA PROCEDURA" in prompt and "WERYFIKACJA" in prompt
    assert "Nie twórz stylu prawnego" in prompt and "Nie wypisuj numerów materiałów" in prompt
def test_support_prompt_uses_titles_full_chunks_and_global_budget():
    full_chunk="A"*1600
    prompt=support_graph.build_technical_support_prompt({
        "client_ref":"K-test","effective_description":"ERR-1234",
        "sources":[
            {"kind":"documentation","title":"Restart usługi","context_role":"match","chunk_text":full_chunk},
            {"kind":"documentation","title":"Restart usługi","context_role":"neighbor","chunk_text":"kolejny krok"},
            *[{"kind":"documentation","title":"Długi dokument","chunk_text":"B"*5000} for _ in range(8)],
        ],
    })
    materials=prompt.split("MATERIAŁY TECHNICZNE:\n",1)[1]
    assert full_chunk in materials and "TYTUŁ: Restart usługi" in materials
    assert "fragment sąsiedni procedury" in materials
    assert len(materials)<=support_graph.LLM_CONTEXT_MAX_CHARS+1
def test_documentation_match_is_expanded_with_adjacent_chunks():
    class Cursor:
        def execute(self,query,params):
            assert params==(7,2,4,2,11)
        def fetchall(self):
            return [
                {"id":"30","kind":"documentation","document_id":7,"chunk_index":2,"chunk_text":"przed","title":"Instrukcja"},
                {"id":"32","kind":"documentation","document_id":7,"chunk_index":4,"chunk_text":"po","title":"Instrukcja"},
            ]
    selected=[{"id":"31","kind":"documentation","document_id":7,"chunk_index":3,
               "chunk_text":"trafienie","title":"Instrukcja","rerank_score":0.9}]
    expanded=support_graph.expand_documentation_neighbors(
        selected,{"program_id":2,"client_id":11},Cursor())
    assert [row["chunk_index"] for row in expanded]==[2,3,4]
    assert [row["context_role"] for row in expanded]==["neighbor","match","neighbor"]
def test_feedback_validation():
    assert validate_feedback("not_helped","")[0]=="incomplete"
    assert validate_feedback("helped","nadal nie pomogło")[0]=="suspicious"
    assert validate_feedback("helped","wykonano poprawnie")[0]=="consistent"
def test_interpretation():
    result=interpret_locally("Błąd ERR-1234 w wersji 2.4.1 podczas zapisu")
    assert result["error_code"] and result["version"]=="2.4.1"
def test_non_finite_scores_are_json_safe(): assert json_safe({"score":float("nan")})=={"score":None}
def test_clarification_answers_reach_model_context():
    enriched=enrich_description("Problem z usługą",{"error_code":"brak","version":"4.2"})
    assert "error_code: brak" in enriched and "version: 4.2" in enriched

def test_state_graph_runs_both_db_agents(monkeypatch):
    monkeypatch.setattr(support_graph,"history_agent_node",lambda state:{"history_candidates":[{"kind":"historical_case","chunk_text":"historia"}]})
    monkeypatch.setattr(support_graph,"documentation_agent_node",lambda state:{"documentation_candidates":[{"kind":"documentation","chunk_text":"instrukcja"}]})
    monkeypatch.setattr(support_graph,"reranking_node",lambda state:{"sources":state["history_candidates"]+state["documentation_candidates"],"step":"answer_generation"})
    monkeypatch.setattr(support_graph,"answer_node",lambda state:{"proposed_answer":"gotowe","status":"awaiting_problem_decision","step":"problem_decision"})
    graph=support_graph.build_graph(None)
    result=graph.invoke({"ticket_id":"test","client_id":1,"program_id":1,"description":"ERR-1234 wersja 1.2.3","answers":{},"history_candidates":[],"documentation_candidates":[]})
    assert {row["kind"] for row in result["sources"]}=={"historical_case","documentation"}
    assert result["proposed_answer"]=="gotowe"

def test_consultation_retrieves_again_for_each_correction(monkeypatch):
    seen={}
    def history(state):
        seen["query"]=state["effective_description"]
        return {"history_candidates":[]}
    monkeypatch.setattr(support_chat,"history_agent_node",history)
    monkeypatch.setattr(support_chat,"documentation_agent_node",lambda state:{"documentation_candidates":[]})
    monkeypatch.setattr(support_chat,"reranking_node",lambda state:{"sources":[{"kind":"documentation","title":"Instrukcja","chunk_text":"Wykonaj krok A"}]})
    monkeypatch.setattr(support_chat,"application_settings",lambda:{})
    monkeypatch.setattr(support_chat,"hybrid_llm_answer",lambda prompt,runtime:(seen.setdefault("prompt",prompt) and "Odpowiedź","external_api",""))
    answer,provider,error,sources=support_chat.answer_consultation(
        question="Sprostowanie: błąd występuje przy eksporcie",conversation=[{"role":"user","content":"Problem przy zapisie"}],
        ticket_description="ERR-1234 w ASW",program_id=2,client_id=7,client_ref="K-test")
    assert "Sprostowanie: błąd występuje przy eksporcie" in seen["query"]
    assert "HISTORIA ROZMOWY" in seen["prompt"] and "Wykonaj krok A" in seen["prompt"]
    assert answer=="Odpowiedź" and provider=="external_api" and not error and len(sources)==1
