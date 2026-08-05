"""
================================================================================
檔案名稱: services/ollama_embedding.py
功能說明: chromadb 相容的 embedding function，透過 Ollama 的 bge-m3 模型產生向量。
         用於取代 chromadb 內建的 all-MiniLM-L6-v2 預設 embedder——實測後者以英文語料
         為主，對中文語意的區分度不足，導致 search_help 檢索結果不準確。
         預設強制跑 CPU（num_gpu=0）：這台機器只有 4GB VRAM，bge-m3 跟
         qwen2.5-coder:7b 搶顯存會導致兩邊互相卸載/重載，回應動輒 50 秒以上；
         機器有 24GB RAM，把 embedding 挪去吃 RAM/CPU，讓 4GB 顯存整個留給 LLM。
================================================================================
"""
import os

import requests
from chromadb import Documents, EmbeddingFunction, Embeddings

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3")
# 設為 "false" 可以改回讓 Ollama 自動決定 GPU/CPU（原本的行為），方便之後 A/B 比較。
OLLAMA_EMBEDDING_FORCE_CPU = os.getenv("OLLAMA_EMBEDDING_FORCE_CPU", "true").strip().lower() != "false"


class OllamaEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self, model: str = OLLAMA_EMBEDDING_MODEL, base_url: str = OLLAMA_BASE_URL):
        self.model = model
        self.base_url = base_url

    @staticmethod
    def name() -> str:
        return "ollama_bge_m3"

    def __call__(self, input: Documents) -> Embeddings:
        payload = {
            "model": self.model,
            "input": list(input),
            # keep_alive 拉長到 30 分鐘：實測 bge-m3 閒置後被 Ollama 卸載，下次呼叫要重新載入
            # 模型，單次查詢可能拉長到 8 秒以上，接近/超過 MCP Streamable HTTP 的請求時限，
            # 導致 SSE 串流中斷 (MCPError: SSE stream ended without a response)。
            "keep_alive": "30m",
        }
        if OLLAMA_EMBEDDING_FORCE_CPU:
            # num_gpu 是「要放幾層到 GPU」，不是 GPU 顆數；設 0 代表全部層數留在 CPU 跑。
            payload["options"] = {"num_gpu": 0}

        resp = requests.post(f"{self.base_url}/api/embed", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["embeddings"]
