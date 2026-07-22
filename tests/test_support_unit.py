from support.ranking import effectiveness,total
from support.security import anonymize
from support.workflow import interpret_locally,validate_feedback
from support.worker import json_safe

def test_ranking_weights(): assert total(1,1,1)==1
def test_effectiveness_has_prior(): assert effectiveness(1,0,0)<1
def test_anonymization():
    value=anonymize("Kontakt jan@example.com, tel. 501 502 503")
    assert "jan@example.com" not in value and "501 502 503" not in value
def test_feedback_validation():
    assert validate_feedback("not_helped","")[0]=="incomplete"
    assert validate_feedback("helped","nadal nie pomogło")[0]=="suspicious"
    assert validate_feedback("helped","wykonano poprawnie")[0]=="consistent"
def test_interpretation():
    result=interpret_locally("Błąd ERR-1234 w wersji 2.4.1 podczas zapisu")
    assert result["error_code"] and result["version"]=="2.4.1"
def test_non_finite_scores_are_json_safe(): assert json_safe({"score":float("nan")})=={"score":None}
