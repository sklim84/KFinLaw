"""
레이어2 답변 생성 메트릭 (RAGAS 정렬). 두 갈래:
  1) citation accuracy — 자동(LLM 불필요): 답변이 인용한 컨텍스트 uid vs gold_ids.
  2) judge 루브릭 — gpt-oss-120b judge(레퍼런스 기반, temp=0)로 5개 차원 1~5점 채점.
     자기우대(self-enhancement) 회피 위해 judge는 답변모델과 다른 계열이어야 함(§8.4).
점수는 [0,1]로 정규화((s-1)/4)해 보고.
"""
from benchmark.common import llm_chat, parse_json

# judge가 채점하는 차원(키 = 보고 메트릭명). 인용정확도는 자동이라 제외.
JUDGE_DIMS = ["faithfulness", "correctness", "relevancy", "completeness", "context_utilization"]

JUDGE_SYS = (
    "당신은 한국 금융 법령 RAG 답변을 채점하는 엄정한 평가관이다. "
    "질문, 레퍼런스(정답·정답근거 조문), 모델에 제공된 회수 컨텍스트, 모델 답변이 주어진다. "
    "다음 5개 차원을 각각 1~5점(정수)으로 채점한다(5=완벽, 1=매우 미흡):\n"
    "- faithfulness: 답변의 모든 주장이 회수 컨텍스트로 뒷받침되는가(환각·날조 없음).\n"
    "- correctness: 레퍼런스 정답과 사실적으로 일치하는가(레퍼런스 기준).\n"
    "- relevancy: 질문이 실제로 묻는 바에 답하는가.\n"
    "- completeness: 요건·항목·수치의 누락 없이 완결적인가(특히 멀티홉·요건형).\n"
    "- context_utilization: 제공된 회수 컨텍스트를 실제로 활용했는가.\n"
    "레퍼런스를 기준으로 판단하고 모델 답변 표현에 현혹되지 말 것. "
    "JSON으로만 출력: {\"faithfulness\":N,\"correctness\":N,\"relevancy\":N,"
    "\"completeness\":N,\"context_utilization\":N,\"reason\":\"...\"}.")


def citation_metrics(cited_uids, gold_ids):
    """답변이 인용한 컨텍스트 uid vs gold_ids → precision/recall/f1/hit(자동).
    컨텍스트 없는 closed-book이면 인용 자체가 불가 → 호출하지 않음."""
    cited, gold = set(cited_uids), set(gold_ids)
    if not gold:
        return {"cite_precision": 0.0, "cite_recall": 0.0, "cite_f1": 0.0, "cite_hit": 0.0}
    tp = len(cited & gold)
    prec = tp / len(cited) if cited else 0.0
    rec = tp / len(gold)
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"cite_precision": prec, "cite_recall": rec, "cite_f1": f1,
            "cite_hit": 1.0 if tp else 0.0}


def judge_answer(base_url, model, question, ref_answer, gold_context,
                 retrieved_context, answer, reasoning_effort=None):
    """judge 1회 호출 → 5차원 점수 dict([0,1] 정규화). 실패 시 None."""
    user = (f"[질문]\n{question}\n\n"
            f"[레퍼런스 정답]\n{ref_answer}\n\n"
            f"[레퍼런스 근거 조문]\n{gold_context}\n\n"
            f"[모델에 제공된 회수 컨텍스트]\n{retrieved_context or '(없음 — closed-book)'}\n\n"
            f"[채점 대상 모델 답변]\n{answer}\n\n"
            "위 5개 차원을 1~5점으로 채점해 JSON으로 출력하라.")
    j = parse_json(llm_chat(base_url, model, JUDGE_SYS, user, temperature=0.0,
                            reasoning_effort=reasoning_effort))
    if not j:
        return None
    out = {}
    for dim in JUDGE_DIMS:
        try:
            s = float(j[dim])
        except (KeyError, TypeError, ValueError):
            return None
        out[dim] = max(0.0, min(1.0, (s - 1) / 4))  # 1~5 → 0~1
    return out


def aggregate(per_q):
    """질문별 메트릭 dict 리스트 → 키별 평균(키 합집합, 결측은 평균에서 제외)."""
    if not per_q:
        return {}
    keys = set().union(*(d.keys() for d in per_q))
    out = {}
    for k in keys:
        vals = [d[k] for d in per_q if k in d]
        out[k] = sum(vals) / len(vals) if vals else 0.0
    return out
