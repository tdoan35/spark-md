This project is Spark MD, Ty and Joyce’s entry for the Dell x NVIDIA AI Hackathon in SF on Oct 25, 2026: an always-on, air-gapped lung CT screening agent running entirely on one Dell Pro Max with GB10. Read docs/spark-md-brief.md before answering anything about scope, stack or plan.

Ty builds; Joyce owns story, pitch, video and QA, and plays the radiologist in the demo. Tailor answers to whichever of them is asking.

The required stack is at least one of OpenClaw / NemoClaw / OpenShell (organizer-confirmed Oct 24). We fix the OpenShell sandbox, Qwen3.8-27B and MONAI + VISTA-3D; the agent harness and serving recipe are chosen Oct 24 (see the decisions log in AGENTS.md). Don’t re-litigate decided items unless asked.
Deterministic code does the medical math; the LLM never assigns Lung-RADS.

Be concise.
