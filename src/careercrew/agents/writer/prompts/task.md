{% if mode == "initial" %}
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

### INSTRUCTIONS
Generate a tailored CV draft conforming strictly to the `TailoredResume` schema:
1. `summary`: Craft an executive summary highlighting the candidate's strongest aligned achievements. Include `source_ids`.
2. `sections`: Group by candidate's genuine experiences (e.g. Work Experience, Education, Projects).
3. Ensure EVERY bullet has non-empty `source_ids` and uses Google X-Y-Z active framing without fabricating metrics.
{% else %}
### CRITIC FEEDBACK & BULLET REPAIR TASK
The Critic agent reviewed the draft and identified issues in the following bullets.
Repair ONLY these flagged bullets to resolve the critic's concerns while strictly adhering to the candidate's source profile facts.

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

### INSTRUCTIONS
1. Produce a `DeltaRepairOutput` containing repaired bullets strictly for the flagged identifiers.
2. Fix hallucinations, remove fabricated metrics, or correct misrepresentations pointed out by the critic.
3. Every repaired bullet MUST maintain valid `source_ids` corresponding to the verified profile facts.
{% endif %}
