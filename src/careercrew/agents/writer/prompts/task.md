{% if mode == "initial" %}
### INSTRUCTIONS & OUTPUT REQUIREMENTS
Generate a complete, tailored resume conforming strictly to the `TailoredResume` schema:
1. `version`: Set version to 1.
2. `summary`: Craft an executive summary highlighting the candidate's strongest aligned achievements. Include non-empty `source_ids`.
3. `sections`: Group by candidate genuine experiences (Work Experience, Projects, Education, etc.).
4. For all optional fields (`organization`, `role_title`, `date_range`), provide their genuine values or null if not applicable.
5. EVERY single bullet MUST carry a non-empty `source_ids` array containing only valid raw bullet IDs from the candidate's profile facts.
6. Apply Google X-Y-Z active framing without hallucinating or extrapolating metrics or dates not in the profile facts.

### TARGET JOB CONTEXT
- **Role**: {{ job.title | default("Software Engineer") }} at {{ job.company | default("Target Company") }}
- **Core Requirements / Skills**: {{ job.requirements | default([]) | join(", ") }}
- **Keywords**: {{ job.keywords | default([]) | join(", ") }}

### CANDIDATE GAP ANALYSIS SUMMARY
- **Matched Strengths**: {{ gap.matched_strengths | default([]) | join("; ") }}
- **Gaps / Recommendations**: {{ gap.recommendations | default([]) | join("; ") }}

### CANDIDATE SOURCE PROFILE (FACTUAL GROUND TRUTH)
Use ONLY the facts below. Every generated bullet MUST link to one or more of these `id` values:
```json
{{ profile_json }}
```
{% else %}
### INSTRUCTIONS & OUTPUT REQUIREMENTS
You are performing a targeted Delta-Repair on specific bullets rejected by the Critic Agent.
1. Return a `DeltaRepairOutput` containing repaired bullets ONLY for the specified bullet identifiers.
2. Address each critic feedback point directly, removing ungrounded claims or hallucinated metrics.
3. Every repaired bullet MUST maintain valid `source_ids` strictly corresponding to the verified profile facts below.
4. Do not alter or output bullets that were already supported.

### FLAGGED BULLETS TO REPAIR
{% for item in flagged_bullets %}
- **Bullet Identifier**: `{{ item.bullet_id }}`
  - **Current Text**: "{{ item.text }}"
  - **Critic Status**: {{ item.status }}
  - **Critic Feedback**: {{ item.critique }}
  - **Associated Source IDs**: {{ item.source_ids | join(", ") }}
  - **Raw Source Facts**:
{% for src_id in item.source_ids %}
    - [{{ src_id }}]: {{ source_facts.get(src_id, "N/A") }}
{% endfor %}
{% endfor %}
{% endif %}
