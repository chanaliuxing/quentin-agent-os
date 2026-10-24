from quentin.council.manager import _fallback_parse

def test_heuristics():
    prose = "The task was successfully completed according to the plan."
    res = _fallback_parse(council_name="done", topic="done_check", raw=prose)
    print("Testing 'Success' prose...")
    print(f"Verdict: {res['verdict']}, Confidence: {res['confidence']}")
    assert res['is_done'] is True
    assert res['confidence'] > 0.8

    prose_fail = "The task is not finished yet, we need to do more."
    res_fail = _fallback_parse(council_name="done", topic="done_check", raw=prose_fail)
    print("Testing 'Failure' prose...")
    print(f"Verdict: {res_fail['verdict']}, Confidence: {res_fail['confidence']}")
    assert res_fail['is_done'] is False

if __name__ == "__main__":
    try:
        test_heuristics()
        print("HEURISTICS_OK")
    except Exception as e:
        print(f"FAILED: {e}")
