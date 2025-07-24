try:
    from InstructorEmbedding import INSTRUCTOR
    USE_INSTRUCTOR = True
except ImportError:
    from sentence_transformers import SentenceTransformer
    USE_INSTRUCTOR = False

_model = None

def get_model():
    global _model
    if _model is None:
        if USE_INSTRUCTOR:
            _model = INSTRUCTOR('hkunlp/instructor-xl')
        else:
            _model = SentenceTransformer('all-mpnet-base-v2')
    return _model

def get_embedding(text, instruction="Represent this IT subject"):
    model = get_model()
    if USE_INSTRUCTOR:
        return model.encode([[instruction, text]])
    else:
        return model.encode([text])[0]
