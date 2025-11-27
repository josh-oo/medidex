import os
from transformers import AutoTokenizer, AutoModel
from dotenv import load_dotenv
import torch

import os

load_dotenv()

MODEL_PATH = os.getenv("MODEL_PATH")
MODEL_REVISION = os.getenv("MODEL_REVISION")
MODEL_DTYPE = os.getenv("MODEL_DTYPE")
TOKENIZER_PATH = os.getenv("TOKENIZER_PATH")
TOKENIZER_REVISION = os.getenv("TOKENIZER_REVISION")
ASPECTS = os.getenv("ASPECTS").split(",")

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
model = model.to(device)

prefix = "".join(["<" + aspect + ">" for aspect in ASPECTS])
dummy_text = prefix + "This is a title of a medical paper"
dummy_input = tokenizer([dummy_text], return_tensors="pt")

traced_model = torch.jit.trace(model, [dummy_input['input_ids'].to(device), dummy_input['attention_mask'].to(device)])
torch.jit.save(traced_model, "traced_model.pt")

#export works but compilation doesn't (for mps device) since there is no kernel yet
"""
options = {
    'pattern_matcher': False, #disable merging attentions into scaled_dot_product op
           }

with torch.no_grad():
    model = model.to(device)
    example_inputs=(dummy_input['input_ids'].to(device), dummy_input['attention_mask'].to(device),)
    seq_dim = torch.export.Dim("sequence_length", min=1 + len(ASPECTS), max=model.config.max_position_embeddings-1)
    exported = torch.export.export(model, example_inputs, dynamic_shapes={"input_ids": {1: seq_dim}, "attention_mask":{ 1: seq_dim}})
    
    output_path = torch._inductor.aoti_compile_and_package(
            exported,
            inductor_configs=options,
            # [Optional] Specify the generated shared library path. If not specified,
            # the generated artifact is stored in your system temp directory.
            package_path="model.pt2",
        )
"""