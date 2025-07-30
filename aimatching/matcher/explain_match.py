import subprocess
import re
from django.conf import settings
from aimatching.matcher.data_extractors import get_subject_text, get_experience_text, get_credentials_text

def generate_mistral_explanation(subject, instructor, full_name, scores, weighted_score, context_strengths=""):
    try:
        subject_text = get_subject_text(subject)

        exp_text = get_experience_text(instructor)
        cred_text = get_credentials_text(instructor)

        strengths = []
        if cred_text:
            strengths.append(f"Credentials: {cred_text}")
        if exp_text:
            strengths.append(f"Experience: {exp_text}")

        strengths_text = "\n".join(strengths) if strengths else "No strong evidence found."

        # Build prompt
        prompt = f"""
        You are an assistant helping the IT department assign instructors to subjects.

        Subject:
        {subject_text}

        Instructor:
        Name: {full_name}

        Evidence:
        {strengths_text}

        Additional Context:
        {context_strengths}

        Task:
        Write a clear and concise explanation (3 sentences) about why {full_name} is a good match for "{subject.name}".
        Focus only on this subject. 
        If multiple instructors seem equally qualified, highlight subject-specific preference, recent relevant activity, or direct tagging that makes them stand out.
        Do not include numeric scores.
        """

        llama_cpp_path = settings.BASE_DIR / "aimatching" / "models" / "llama-run.exe"
        mistral_model_path = settings.BASE_DIR / "aimatching" / "models" / "mistral-7b-instruct-v0.1.Q6_K.gguf"

        result = subprocess.run(
            [str(llama_cpp_path), str(mistral_model_path), prompt],
            capture_output=True,
            text=True,
            check=True
        )

        cleaned_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', result.stdout)
        return cleaned_output.strip()

    except subprocess.CalledProcessError as e:
        return f"⚠️ Mistral error: {e.stderr.strip()}"
    except Exception as e:
        return f"⚠️ Unexpected error: {str(e)}"
