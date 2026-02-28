from pathlib import Path
from JSON2Python_Quiz import load_json, parse_questions

p = Path('JSON_Files/Tomsho_NetEssentials9e_Chapter07_KnowledgeChecks.json')
data = load_json(p)
qs = parse_questions(data)
print('count', len(qs))
for q in qs:
    print('qid', q.qid, 'opts', q.options, 'answer', q.answer)
