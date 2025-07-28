from InstructorEmbedding import INSTRUCTOR
import torch


_model = None

INSTRUCTIONS = {
            "subject": "Embed this IT course subject to find suitable instructors",
            "teaching": "Embed this instructor's past teaching subjects for relevance to an IT course",
            "credentials": "Embed this instructor's academic and professional qualifications for teaching IT",
            "experience": "Embed this instructor's relevant work experience for teaching an IT subject",
            "preference": "Embed this instructor's preferred IT subjects to teach"
        }

def get_model():
    global _model
    if _model is None:
        _model = INSTRUCTOR('hkunlp/instructor-xl')
        _model.to("cuda" if torch.cuda.is_available() else "cpu")
    return _model

def get_embedding(text, instruction=None):
    if instruction is None:
        instruction = INSTRUCTIONS["subject"]
    model = get_model()
    return model.encode([[instruction, text]])
