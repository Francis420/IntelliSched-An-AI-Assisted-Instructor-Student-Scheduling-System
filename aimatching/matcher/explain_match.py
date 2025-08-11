import subprocess
import re
from django.conf import settings
from aimatching.matcher.data_extractors import get_subject_text, get_experience_text, get_credentials_text

def generate_mistral_explanation(subject, instructor, full_name, primary_factor, primary_score, primary_evidence):
    """
    Generate an explanation for why an instructor is a strong match for a subject,
    based ONLY on the strongest matching factor and its supporting evidence.
    """
    try:
        prompt = f"""
You are an assistant helping the IT department assign instructors to subjects.

Subject:
{subject.name}

Instructor:
Name: {full_name}

Primary Match Factor:
{primary_factor} (Score: {primary_score})

Evidence:
{primary_evidence}

Task:
Write a short, clear explanation (max 3 sentences) about why {full_name} is a strong match for "{subject.name}".
Focus only on the primary factor and evidence provided.
Do not include numeric scores in the explanation.
"""

        # Paths to llama.cpp runner and model
        llama_cpp_path = settings.BASE_DIR / "aimatching" / "models" / "llama-run.exe"
        mistral_model_path = settings.BASE_DIR / "aimatching" / "models" / "mistral-7b-instruct-v0.1.Q6_K.gguf"

        # Run local mistral model
        result = subprocess.run(
            [str(llama_cpp_path), str(mistral_model_path), prompt],
            capture_output=True,
            text=True,
            check=True
        )

        # Remove terminal color codes if present
        cleaned_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', result.stdout)
        return cleaned_output.strip()

    except subprocess.CalledProcessError as e:
        return f"⚠️ Mistral error: {e.stderr.strip()}"
    except Exception as e:
        return f"⚠️ Unexpected error: {str(e)}"

