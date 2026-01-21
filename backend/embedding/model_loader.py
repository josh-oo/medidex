import os
from transformers import AutoTokenizer, AutoModel
from dotenv import load_dotenv
import torch
import torch.onnx

import os

load_dotenv()

MODEL_PATH = os.getenv("EMBEDDING_MODEL_PATH")
MODEL_REVISION = os.getenv("EMBEDDING_MODEL_REVISION")
MODEL_DTYPE = os.getenv("EMBEDDING_MODEL_DTYPE")
TOKENIZER_PATH = os.getenv("EMBEDDING_MODEL_TOKENIZER_PATH")
TOKENIZER_REVISION = os.getenv("EMBEDDING_MODEL_TOKENIZER_REVISION")
ASPECTS = os.getenv("EMBEDDING_MODEL_ASPECTS").split(",")

torch.set_default_dtype(torch.float32)

device = (
            "cuda" if torch.cuda.is_available()
            else "mps" if torch.backends.mps.is_available()
            else "cpu"
        )

#TODO check if "sdpa" is implemented now
attn_implementation = "eager" if device == "mps" else "sdpa"
model = AutoModel.from_pretrained(MODEL_PATH, revision=MODEL_REVISION, torch_dtype=MODEL_DTYPE, attn_implementation=attn_implementation, torchscript=True)
model.register_buffer("position_ids", torch.relu(torch.arange(model.config.max_position_embeddings + len(ASPECTS)).expand((1, -1))  - len(ASPECTS)), persistent=False)
tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_PATH, revision=TOKENIZER_REVISION)

tokenizer.add_tokens([f"<{aspect}>" for aspect in ASPECTS])
tokenizer.save_pretrained("tokenizer")

model.eval()
model = model.to(device).to(torch.float32)#ONNX can not be exported to bf16

prefix = "".join(["<" + aspect + ">" for aspect in ASPECTS])
dummy_text = prefix + "This is a title of a medical paper"
dummy_input = tokenizer([dummy_text], return_tensors="pt")

# Prepare dummy inputs for ONNX export
dummy_input_ids = dummy_input['input_ids'].to(device)
dummy_attention_mask = dummy_input['attention_mask'].to(device)
onnx_inputs = (dummy_input_ids, dummy_attention_mask)

dynamic_shapes = {
    "input_ids": {0: "batch_size", 1: "sequence_length"},
    "attention_mask": {0: "batch_size", 1: "sequence_length"},
}

# Export the model to ONNX
onnx_path = "model.onnx"
torch.onnx.export(
    model,
    onnx_inputs,
    onnx_path,
    input_names=["input_ids", "attention_mask"],
    output_names=["output"],
    dynamic_shapes=dynamic_shapes,
    opset_version=18,
    do_constant_folding=True,
    dynamo=True,
)
print(f"ONNX model saved to {onnx_path}")