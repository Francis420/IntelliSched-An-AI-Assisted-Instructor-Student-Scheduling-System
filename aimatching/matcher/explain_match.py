import subprocess
import re
from django.conf import settings

def generate_mistral_explanation(subject, instructor, full_name, primary_factor, primary_score, primary_evidence):
    """
    Generate an explanation for why an instructor is a strong match for a subject,
    based ONLY on the strongest matching factor and its supporting evidence.
    """
    
    # 1. Prepare Subject Context (Match the richness of your data extractor)
    # Using 'or' handles None/Null values gracefully
    s_code = subject.code or ""
    s_name = subject.name or ""
    s_desc = subject.description or "No description available."
    s_topics = subject.subjectTopics or "No topics listed."

    try:
        # 2. Construct a clearer, context-rich prompt
        prompt = f"""
You are an assistant helping the IT department assign instructors to subjects.

Target Subject:
{s_code} - {s_name}
Description: {s_desc}
Topics: {s_topics}

Candidate Instructor:
Name: {full_name}

Primary Match Factor:
{primary_factor} (Confidence: {primary_score:.2f})

Supporting Evidence:
{primary_evidence}

Task:
Write a short, professional explanation (2-3 sentences max) justifying this assignment.
Explain exactly how the evidence supports the subject's topics or description.
Do NOT mention the numeric confidence score.
"""

        # 3. Path Setup
        llama_cpp_path = settings.BASE_DIR / "aimatching" / "models" / "llama-run.exe"
        mistral_model_path = settings.BASE_DIR / "aimatching" / "models" / "mistral-7b-instruct-v0.1.Q6_K.gguf"

        # 4. Run Inference
        result = subprocess.run(
            [
                str(llama_cpp_path),
                '--verbose',
                str(mistral_model_path),
                prompt
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,  # 2-minute timeout
        )

        # 5. Output Cleaning
        # Remove ANSI color codes often output by llama.cpp
        cleaned_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', result.stdout)
        
        # Optional: If your llama-run.exe outputs the prompt back, you might want to split it.
        # For now, we return the full stripped output as requested.
        return cleaned_output.strip()

    except subprocess.TimeoutExpired:
        return "⚠️ Mistral error: Model inference timed out."
    except subprocess.CalledProcessError as e:
        err = e.stderr or "No stderr output"
        return f"⚠️ Mistral error: {err.strip()}"
    except Exception as e:
        return f"⚠️ Unexpected error: {str(e)}"