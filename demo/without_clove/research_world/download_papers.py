#!/usr/bin/env python3
"""
Download research papers for the Research World.

Sources:
- PubMed Central (free full-text papers)
- arXiv (preprints)
"""

import os
import sys
import urllib.request
import urllib.parse
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data" / "pdfs"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def download_from_pmc(pmc_id: str) -> bool:
    """Download paper from PubMed Central."""
    url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"
    output = DATA_DIR / f"{pmc_id}.pdf"

    if output.exists():
        print(f"  Already exists: {pmc_id}")
        return True

    try:
        print(f"  Downloading: {pmc_id}...")
        urllib.request.urlretrieve(url, output)
        print(f"  Saved: {output.name}")
        return True
    except Exception as e:
        print(f"  Failed: {e}")
        return False


def download_from_arxiv(arxiv_id: str) -> bool:
    """Download paper from arXiv."""
    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    safe_name = arxiv_id.replace("/", "_").replace(".", "_")
    output = DATA_DIR / f"arxiv_{safe_name}.pdf"

    if output.exists():
        print(f"  Already exists: {arxiv_id}")
        return True

    try:
        print(f"  Downloading: {arxiv_id}...")
        urllib.request.urlretrieve(url, output)
        print(f"  Saved: {output.name}")
        return True
    except Exception as e:
        print(f"  Failed: {e}")
        return False


def create_text_document(filename: str, content: str):
    """Create a text document."""
    output = DATA_DIR / filename
    output.write_text(content)
    print(f"  Created: {filename}")


# Sample diabetes research content
DIABETES_RESEARCH = """
# Comprehensive Review: Type 2 Diabetes Treatment Landscape 2024

## Executive Summary

Type 2 diabetes mellitus (T2DM) affects approximately 537 million adults globally,
with prevalence expected to rise to 783 million by 2045. This review examines
current treatment approaches, emerging therapies, and evidence-based recommendations.

## First-Line Therapy: Metformin

Metformin remains the cornerstone of T2DM management:
- Mechanism: Reduces hepatic glucose production via AMPK activation
- Efficacy: HbA1c reduction of 1.0-1.5%
- Benefits: Weight neutral, cardiovascular protection, low cost
- Limitations: GI side effects, contraindicated in severe renal impairment

## Second-Line Options

### SGLT2 Inhibitors (Empagliflozin, Dapagliflozin, Canagliflozin)
- Mechanism: Block renal glucose reabsorption
- HbA1c reduction: 0.5-1.0%
- Additional benefits:
  * Cardiovascular risk reduction (EMPA-REG: 38% CV death reduction)
  * Heart failure hospitalization reduction (35%)
  * Renal protection (CREDENCE trial)
- Weight loss: 2-3 kg average
- Risks: Genital infections, DKA (rare)

### GLP-1 Receptor Agonists (Semaglutide, Liraglutide, Dulaglutide)
- Mechanism: Enhance glucose-dependent insulin secretion
- HbA1c reduction: 1.0-1.8%
- Weight loss: Up to 15% with semaglutide 2.4mg
- Cardiovascular benefits: LEADER showed 13% MACE reduction
- Side effects: Nausea, vomiting (usually transient)

### DPP-4 Inhibitors (Sitagliptin, Linagliptin)
- Mechanism: Prevent incretin degradation
- HbA1c reduction: 0.5-0.8%
- Weight neutral
- Well tolerated but modest efficacy

## Emerging Therapies

### Tirzepatide (Dual GIP/GLP-1 Agonist)
- SURPASS trials: Up to 2.4% HbA1c reduction
- Weight loss: Up to 22.5%
- Approved for T2DM, obesity indication pending

### Oral Semaglutide
- First oral GLP-1 agonist
- Similar efficacy to injectable formulation
- Requires specific administration protocol

## Treatment Algorithm

1. Lifestyle modification + Metformin (first-line)
2. Add SGLT2i or GLP-1 RA based on:
   - Cardiovascular disease: Prefer agents with proven CV benefit
   - Heart failure: SGLT2 inhibitor preferred
   - CKD: SGLT2 inhibitor or GLP-1 RA with renal benefit
   - Obesity: GLP-1 RA preferred
3. Consider combination therapy for HbA1c >9%
4. Insulin when other agents insufficient

## Key Clinical Trials Summary

| Trial | Drug | Primary Outcome | Result |
|-------|------|-----------------|--------|
| EMPA-REG | Empagliflozin | CV death, MI, stroke | 14% reduction |
| LEADER | Liraglutide | MACE | 13% reduction |
| SUSTAIN-6 | Semaglutide | MACE | 26% reduction |
| CREDENCE | Canagliflozin | Renal composite | 30% reduction |
| SURPASS-2 | Tirzepatide | HbA1c | Superior to semaglutide |

## Conclusions

Modern T2DM management has evolved beyond glucose control to include
cardiovascular and renal protection. Individualized therapy selection
based on comorbidities, patient preferences, and treatment goals is essential.

## References

1. American Diabetes Association. Standards of Care 2024
2. Davies MJ, et al. Diabetes Care 2022
3. Zinman B, et al. EMPA-REG OUTCOME. N Engl J Med 2015
4. Marso SP, et al. LEADER. N Engl J Med 2016
5. Perkovic V, et al. CREDENCE. N Engl J Med 2019
"""

SGLT2_DEEP_DIVE = """
# SGLT2 Inhibitors: Mechanisms and Clinical Evidence

## Pharmacology

### Mechanism of Action
SGLT2 (Sodium-Glucose Cotransporter 2) is responsible for ~90% of renal
glucose reabsorption in the proximal tubule. SGLT2 inhibitors block this
transporter, causing glucosuria of 70-80g/day.

### Pharmacokinetics
- Empagliflozin: t1/2 = 12.4h, 86% protein bound
- Dapagliflozin: t1/2 = 12.9h, 91% protein bound
- Canagliflozin: t1/2 = 10.6-13.1h, 99% protein bound

## Cardiovascular Mechanisms

Beyond glucose lowering, SGLT2i provide CV benefits through:

1. Hemodynamic Effects
   - Reduced preload (osmotic diuresis)
   - Reduced afterload (decreased arterial stiffness)
   - Blood pressure reduction (3-5 mmHg systolic)

2. Metabolic Effects
   - Shift from glucose to fatty acid/ketone oxidation
   - Increased ketone bodies (efficient myocardial fuel)
   - Reduced lipotoxicity

3. Direct Cardiac Effects
   - Improved myocardial energetics
   - Reduced oxidative stress
   - Anti-inflammatory effects

## Renal Protection Mechanisms

1. Reduced intraglomerular pressure
   - Restoration of tubuloglomerular feedback
   - Afferent arteriole vasoconstriction

2. Reduced hyperfiltration
   - Decreased single-nephron GFR
   - Protection against progressive nephron loss

3. Metabolic effects
   - Reduced renal oxygen consumption
   - Decreased inflammation and fibrosis

## Major Clinical Trials

### EMPA-REG OUTCOME (2015)
- N = 7,020 with T2DM and established CVD
- Empagliflozin vs placebo
- Primary: 14% MACE reduction (HR 0.86)
- CV death: 38% reduction
- HF hospitalization: 35% reduction

### CANVAS Program (2017)
- N = 10,142 with T2DM and high CV risk
- Canagliflozin vs placebo
- Primary: 14% MACE reduction (HR 0.86)
- Signal for increased amputation (addressed)

### DECLARE-TIMI 58 (2019)
- N = 17,160 with T2DM (broader population)
- Dapagliflozin vs placebo
- CV death/HF hospitalization: 17% reduction
- Established CVD and risk factor subgroups benefited

### DAPA-HF (2019)
- N = 4,744 with HFrEF (with or without diabetes)
- Dapagliflozin vs placebo
- Primary: 26% reduction in CV death/HF worsening
- Benefit in non-diabetic patients established

### CREDENCE (2019)
- N = 4,401 with T2DM and CKD
- Canagliflozin vs placebo
- Primary renal outcome: 30% reduction
- Stopped early for efficacy

## Safety Considerations

### Common
- Genital mycotic infections (5-10%)
- Urinary tract infections (modest increase)
- Volume depletion (especially elderly)

### Rare but Serious
- Diabetic ketoacidosis (euglycemic)
  * Risk factors: Surgery, fasting, illness
  * Management: Hold during acute illness
- Fournier's gangrene (very rare)

### Monitoring
- Renal function at baseline and periodically
- Volume status in elderly/diuretic users
- Ketones if symptomatic during illness

## Clinical Recommendations

1. First-line add-on for T2DM with:
   - Established ASCVD
   - Heart failure
   - CKD (eGFR ≥20-25)

2. Consider regardless of HbA1c in high-risk patients

3. Continue even as eGFR declines (cardiorenal benefit persists)

4. Avoid in Type 1 diabetes, recurrent DKA, severe renal impairment
"""

GLP1_WEIGHT_LOSS = """
# GLP-1 Receptor Agonists: The Weight Loss Revolution

## Overview

GLP-1 receptor agonists have transformed obesity treatment, with semaglutide
achieving unprecedented weight loss in clinical trials.

## Mechanism of Weight Loss

### Central Effects
- Hypothalamic appetite suppression
- Reduced food reward signaling
- Increased satiety
- Delayed gastric emptying

### Peripheral Effects
- Improved insulin sensitivity
- Reduced hepatic lipogenesis
- Possible increased energy expenditure

## Clinical Evidence for Weight Loss

### STEP Trials (Semaglutide 2.4mg for Obesity)

**STEP 1 (N=1,961)**
- Population: Obesity without diabetes
- Result: 14.9% weight loss vs 2.4% placebo
- 86% achieved ≥5% weight loss
- 32% achieved ≥20% weight loss

**STEP 2 (N=1,210)**
- Population: Obesity with T2DM
- Result: 9.6% weight loss vs 3.4% placebo
- HbA1c reduction: 1.6%

**STEP 3 (N=611)**
- Population: Obesity + intensive behavioral therapy
- Result: 16.0% weight loss vs 5.7% placebo

**STEP 4 (N=902)**
- Design: Withdrawal study
- Result: Continued treatment maintained loss
- Weight regain of ~7% after stopping

### SURMOUNT Trials (Tirzepatide for Obesity)

**SURMOUNT-1 (N=2,539)**
- Population: Obesity without diabetes
- Results by dose:
  * 5mg: 15.0% weight loss
  * 10mg: 19.5% weight loss
  * 15mg: 20.9% weight loss
- 57% achieved ≥20% weight loss at highest dose

### Head-to-Head Comparison

**SURPASS-2**
- Tirzepatide vs Semaglutide 1mg in T2DM
- Weight loss: Tirzepatide superior at all doses
- HbA1c: Tirzepatide superior

## Cardiovascular Outcomes

### SELECT Trial (2023)
- Semaglutide 2.4mg in obesity WITHOUT diabetes
- N = 17,604 with overweight/obesity and CVD
- Primary outcome: 20% MACE reduction
- Paradigm shift: CV benefit independent of diabetes

## Practical Considerations

### Dosing
- Start low, titrate slowly to minimize GI effects
- Semaglutide: 0.25mg weekly → 2.4mg over 16-20 weeks
- Tirzepatide: 2.5mg weekly → 15mg over 20 weeks

### Patient Selection
- BMI ≥30, or ≥27 with comorbidity
- Motivated for lifestyle changes
- No contraindications (MTC history, MEN2)

### Managing Side Effects
- Nausea: Most common, usually transient
- Advise smaller meals, avoid high-fat foods
- Slow titration if persistent

### Duration of Therapy
- Weight regain after discontinuation
- Likely long-term/indefinite treatment needed
- Insurance coverage remains barrier

## Future Directions

1. Oral formulations (oral semaglutide available)
2. Triple agonists (GLP-1/GIP/glucagon)
3. Combination approaches
4. Earlier intervention in obesity
5. Addressing weight maintenance

## Summary

GLP-1 RAs represent a paradigm shift in obesity treatment, achieving
weight loss approaching bariatric surgery with proven cardiovascular
benefits. Tirzepatide may offer even greater efficacy.
"""


def main():
    """Create research documents."""
    print("\nPreparing research data...")
    print("-" * 40)

    # Create text documents
    create_text_document("diabetes_treatment_review_2024.txt", DIABETES_RESEARCH)
    create_text_document("sglt2_inhibitors_deep_dive.txt", SGLT2_DEEP_DIVE)
    create_text_document("glp1_weight_loss_revolution.txt", GLP1_WEIGHT_LOSS)

    print("-" * 40)
    print(f"\nData ready in: {DATA_DIR}")
    print(f"Total documents: {len(list(DATA_DIR.glob('*.txt')))}")

    print("\nTo add more documents:")
    print(f"  cp your_papers.pdf {DATA_DIR}/")
    print(f"  cp your_notes.txt {DATA_DIR}/")


if __name__ == "__main__":
    main()
