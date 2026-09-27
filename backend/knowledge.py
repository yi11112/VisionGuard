import json
import re
from pathlib import Path
from rank_bm25 import BM25Okapi

def tokenize(text):
    return re.findall(r'[a-z0-9_]+|[\u4e00-\u9fff]', text.lower())

class Knowledge:
    def __init__(self, path):
        self.docs = json.loads(Path(path).read_text(encoding='utf-8'))
        self.index = BM25Okapi([tokenize(d['title'] + d['text'] + d['event_type']) for d in self.docs])
        self.vectors = None
    def search(self, query, event_type=None):
        scores = self.index.get_scores(tokenize(query))
        ranked = sorted(zip(self.docs, scores), key=lambda x: x[1], reverse=True)
        return [d | {'retrieval_score': round(float(score), 3), 'retrieval_method':'BM25'} for d, score in ranked
                if score > 0 and (not event_type or d['event_type'] == event_type)][:3]

    async def search_hybrid(self, query, event_type, ollama_url):
        import httpx
        import faiss
        import numpy as np
        corpus=[d['title']+' '+d['text'] for d in self.docs]
        inputs=corpus+[query] if self.vectors is None else [query]
        async with httpx.AsyncClient(timeout=120) as client:
            response=await client.post(ollama_url+'/api/embed',json={
                'model':'bge-m3','input':inputs,'keep_alive':0})
            response.raise_for_status()
            vectors=np.asarray(response.json()['embeddings'],dtype=np.float32)
        if vectors.ndim!=2 or len(vectors)!=len(inputs) or not np.isfinite(vectors).all():
            raise ValueError('Invalid embedding response')
        faiss.normalize_L2(vectors)
        if self.vectors is None: self.vectors=vectors[:-1].copy()
        index=faiss.IndexFlatIP(self.vectors.shape[1]); index.add(self.vectors)
        similarities,order=index.search(vectors[-1:],len(self.docs))
        dense_rank={int(i):rank+1 for rank,i in enumerate(order[0])}
        dense_score={int(i):float(s) for i,s in zip(order[0],similarities[0])}
        sparse=self.index.get_scores(tokenize(query))
        sparse_order=sorted(range(len(self.docs)),key=lambda i:sparse[i],reverse=True)
        sparse_rank={i:rank+1 for rank,i in enumerate(sparse_order)}
        results=[]
        for i,d in enumerate(self.docs):
            if d['event_type']!=event_type: continue
            if sparse[i]<=0 and dense_score[i]<0.35: continue
            score=1/(60+dense_rank[i])+1/(60+sparse_rank[i])
            results.append(d|{'retrieval_score':round(score,5),'cosine_similarity':round(dense_score[i],4),
                              'retrieval_method':'BGE-M3 + FAISS + BM25 / RRF'})
        return sorted(results,key=lambda d:d['retrieval_score'],reverse=True)[:3]

