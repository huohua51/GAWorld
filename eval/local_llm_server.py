"""Tiny Ollama-compatible API server using HuggingFace transformers.
Start: CUDA_VISIBLE_DEVICES=3 python3 eval/local_llm_server.py --port 11436
Then in wrapper: point ollama provider to http://localhost:11436/api/generate
"""
import argparse
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
tokenizer = None
model = None

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        req = json.loads(body)
        prompt = req.get("prompt", req.get("messages", [{"role": "user", "content": "hello"}])[-1]["content"])
        stream = req.get("stream", False)

        messages = [{"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors="pt").to(model.device)

        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=256, do_sample=True, temperature=0.3)

        resp = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            self.wfile.write(json.dumps({"response": resp, "done": True}).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"response": resp, "done": True}).encode())

    def log_message(self, *a):
        pass  # suppress logs

def main():
    global tokenizer, model
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=11436)
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args()

    print(f"Loading {args.model}...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float16, device_map="auto")
    model.eval()
    print(f"Loaded on {model.device}, memory: {torch.cuda.memory_allocated()/1e9:.2f}GB", flush=True)

    server = HTTPServer(("0.0.0.0", args.port), Handler)
    print(f"Serving on http://localhost:{args.port}", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    main()
