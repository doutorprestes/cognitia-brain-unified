# Issue #4 — Classificação ML

**Labels:** `fase-4`, `ml`, `classificador`
**Estimate:** 2h

## Descrição

Implementar classificador de relevância usando SetFit + MiniLM para filtrar grants/artigos úteis vs não-úteis.

## Tarefas

- [ ] Criar `src/ml/classifier.py` com classe `RelevanceClassifier`
- [ ] Implementar `treinar(textos, labels)` — treina com poucos exemplos
- [ ] Implementar `prever(texto) → (label, confidence)` — retorna predição e confiança
- [ ] Implementar `salvar_modelo(path)` e `carregar_modelo(path)`
- [ ] Criar função de embedding usando `paraphrase-multilingual-MiniLM-L12-v2`
- [ ] Implementar `get_confidence(text) → float` (probabilidade da classe positiva)
- [ ] Integrar ChromaDB para busca semântica
- [ ] Integrar classificador .NET (buscador_de_grants) via bridge se necessário
- [ ] Criar `tests/test_classifier.py`

## Modelo Proposto

```python
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression

class RelevanceClassifier:
    def __init__(self):
        self.encoder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.classifier = LogisticRegression()
    
    def treinar(self, texts, labels):
        embeddings = self.encoder.encode(texts)
        self.classifier.fit(embeddings, labels)
    
    def prever(self, text):
        embedding = self.encoder.encode([text])
        proba = self.classifier.predict_proba(embedding)[0]
        label = 1 if proba[1] > 0.5 else 0
        confidence = max(proba)
        return label, confidence
```

## Critérios de Aceite

- [ ] Treinar com 20+ exemplos funciona sem erros
- [ ] `prever()` retorna label (0 ou 1) e confiança (0.0 a 1.0)
- [ ] Modelo salva/carrega corretamente
- [ ] Testes passam: `pytest tests/test_classifier.py -v`
- [ ] Inferência roda em CPU (< 100ms por predição)

## Output Esperado

```python
clf = RelevanceClassifier()
clf.treinar(texts_treinamento, labels)
label, conf = clf.prever("Edital aberto para pesquisa em IA")
# label=1, confidence=0.87
```
