"""
benchmarks/generate_architecture_diagram.py
────────────────────────────────────────────────────────
Generates a modern, publication-quality vector PDF architecture diagram 
for the FedGuard Governance Control Plane & Conclave Reference Implementation.
Output: research_paper/figures/fig_fedguard_architecture.pdf (300+ DPI PDF)
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

OUTPUT_PATH = "research_paper/figures/fig_fedguard_architecture.pdf"
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

# Publication Plot Styling Configuration
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "font.size": 8.5,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

def create_architecture_diagram():
    fig, ax = plt.subplots(figsize=(7.1, 4.6), dpi=300)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')

    # Color Palette - Professional Modern IEEE Theme
    C_BG_CARD = "#ffffff"
    C_BORDER_DEFAULT = "#94a3b8"
    
    # Layer 1: Clients & Attestation (Teal)
    C_L1_BG = "#f0fdf4"
    C_L1_BORDER = "#0d9488"
    C_L1_TEXT = "#064e3b"
    C_L1_BOX = "#ccfbf1"

    # Layer 2: Governance Control Plane (Indigo)
    C_L2_BG = "#eef2ff"
    C_L2_BORDER = "#4f46e5"
    C_L2_TEXT = "#1e1b4b"
    C_L2_BOX = "#e0e7ff"

    # Layer 3: Crypto & Aggregation Engine (Slate Blue)
    C_L3_BG = "#f8fafc"
    C_L3_BORDER = "#334155"
    C_L3_TEXT = "#0f172a"
    C_L3_BOX = "#e2e8f0"

    # Layer 4: Audit Ledger & Unlearning (Rose/Crimson)
    C_L4_BG = "#fff1f2"
    C_L4_BORDER = "#e11d48"
    C_L4_TEXT = "#881337"
    C_L4_BOX = "#ffe4e6"

    # Helper function to draw rounded boxes
    def draw_card(x, y, w, h, bg, border, title="", title_color="#000000", lw=1.2, r=1.5):
        box = patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0,rounding_size={r}",
            facecolor=bg, edgecolor=border, linewidth=lw, zorder=1
        )
        ax.add_patch(box)
        if title:
            ax.text(x + 1.5, y + h - 2.8, title, fontsize=9.5, fontweight='bold', color=title_color, zorder=2)

    def draw_subbox(x, y, w, h, bg, border, text_lines, text_color="#000000", lw=1.0, align='center', r=1.0):
        box = patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0,rounding_size={r}",
            facecolor=bg, edgecolor=border, linewidth=lw, zorder=3
        )
        ax.add_patch(box)
        
        n_lines = len(text_lines)
        for i, line in enumerate(text_lines):
            line_y = y + h/2 + (n_lines/2 - i - 0.5) * 2.8
            if align == 'center':
                ax.text(x + w/2, line_y, line[0], fontsize=line[1], fontweight=line[2], color=text_color, ha='center', va='center', zorder=4)
            else:
                ax.text(x + 1.5, line_y, line[0], fontsize=line[1], fontweight=line[2], color=text_color, ha='left', va='center', zorder=4)

    def draw_arrow(x1, y1, x2, y2, color="#475569", style='->', lw=1.2, text="", text_pos=None):
        ax.annotate(
            "", xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle=style, color=color, lw=lw, mutation_scale=10),
            zorder=5
        )
        if text and text_pos:
            ax.text(text_pos[0], text_pos[1], text, fontsize=7.5, fontweight='bold', color=color, ha='center', va='center', zorder=6,
                    bbox=dict(boxstyle="square,pad=0.15", facecolor="#ffffff", edgecolor="none", alpha=0.9))

    # ==================== MAIN ARCHITECTURE SECTIONS ====================

    # Title Banner at Top
    ax.text(50, 97.5, "FedGuard Governance Control Plane & Conclave Architecture Overview", 
            fontsize=11, fontweight='bold', color="#0f172a", ha='center', va='center')

    # 1. LAYER 1: CLIENT PARTICIPANTS & HARDWARE ATTESTATION (TOP ROW)
    draw_card(2, 73, 96, 21, C_L1_BG, C_L1_BORDER, "Participant Layer: Multi-Institutional Edge Nodes & Hardware Root-of-Trust", C_L1_TEXT)

    # Client Nodes Boxes
    draw_subbox(4, 75, 27, 14, C_L1_BOX, C_L1_BORDER, [
        ("Client Node u (Hospital / Bank)", 8.5, 'bold'),
        ("mTLS 1.3 X.509 Certificate", 7.5, 'normal'),
        ("TPM 2.0 PCR Attestation Quote", 7.5, 'normal'),
        ("Local PyTorch Model Update Δ_u", 7.5, 'normal')
    ], C_L1_TEXT)

    draw_subbox(36.5, 75, 27, 14, C_L1_BOX, C_L1_BORDER, [
        ("Client Node v (Enterprise Silo)", 8.5, 'bold'),
        ("mTLS 1.3 X.509 Certificate", 7.5, 'normal'),
        ("TPM 2.0 PCR Attestation Quote", 7.5, 'normal'),
        ("Local PyTorch Model Update Δ_v", 7.5, 'normal')
    ], C_L1_TEXT)

    draw_subbox(69, 75, 27, 14, C_L1_BOX, C_L1_BORDER, [
        ("Client Node N (Edge Participant)", 8.5, 'bold'),
        ("mTLS 1.3 X.509 Certificate", 7.5, 'normal'),
        ("Software Certificate Fallback", 7.5, 'normal'),
        ("Local PyTorch Model Update Δ_N", 7.5, 'normal')
    ], C_L1_TEXT)

    # Arrows from Layer 1 to Layer 2
    draw_arrow(17.5, 75, 17.5, 68, C_L1_BORDER, '->', 1.2, "TLS 1.3 / Quote", (17.5, 71.5))
    draw_arrow(50, 75, 50, 68, C_L1_BORDER, '->', 1.2, "TLS 1.3 / Quote", (50, 71.5))
    draw_arrow(82.5, 75, 82.5, 68, C_L1_BORDER, '->', 1.2, "TLS 1.3 / Quote", (82.5, 71.5))


    # 2. LAYER 2: DECOUPLED GOVERNANCE CONTROL PLANE (MIDDLE TOP ROW)
    draw_card(2, 38, 96, 30, C_L2_BG, C_L2_BORDER, "FedGuard Decoupled Governance Control Plane Engine", C_L2_TEXT)

    # Module 2A: ABAC/RBAC Policy Verification Engine
    draw_subbox(4, 40.5, 28, 23.5, C_L2_BOX, C_L2_BORDER, [
        ("ABAC / RBAC Policy Engine", 8.5, 'bold'),
        ("• X.509 Certificate Validation", 7.5, 'normal'),
        ("• Role & Attribute Matching", 7.5, 'normal'),
        ("• TPM 2.0 Quote Measurement", 7.5, 'normal'),
        ("• Dynamic Access Control", 7.5, 'normal'),
        ("• Statutory Mappings (HIPAA/GDPR)", 7.0, 'bold')
    ], C_L2_TEXT, align='left')

    # Module 2B: Governance Mode & Threshold SecAgg Handler
    draw_subbox(36, 40.5, 28, 23.5, C_L2_BOX, C_L2_BORDER, [
        ("Mode Handler & SecAgg", 8.5, 'bold'),
        ("• Mode Negotiation:", 7.5, 'bold'),
        ("   SECURE_AGGREGATION", 7.0, 'normal'),
        ("   BYZANTINE_RESILIENT", 7.0, 'normal'),
        ("• Pairwise ECDH Key Exchange", 7.5, 'normal'),
        ("• Shamir Secret Sharing (k-of-N)", 7.5, 'normal')
    ], C_L2_TEXT, align='left')

    # Module 2C: RDP Privacy Accountant & Unlearning Trigger
    draw_subbox(68, 40.5, 28, 23.5, C_L2_BOX, C_L2_BORDER, [
        ("Privacy & Unlearning Engine", 8.5, 'bold'),
        ("• Rényi DP Budget Accountant", 7.5, 'normal'),
        ("  (Tracks (ε_t, δ_t) vs ε_max)", 7.0, 'normal'),
        ("• Gaussian Noise Injector", 7.5, 'normal'),
        ("• GDPR Art. 17 Revocation Handler", 7.5, 'normal'),
        ("• FedEraser Purification Trigger", 7.0, 'bold')
    ], C_L2_TEXT, align='left')

    # Arrows inside Layer 2
    draw_arrow(32, 52, 36, 52, C_L2_BORDER, '->', 1.0)
    draw_arrow(64, 52, 68, 52, C_L2_BORDER, '->', 1.0)

    # Arrows from Layer 2 to Layer 3
    draw_arrow(18, 40.5, 18, 33, C_L2_BORDER, '->', 1.2, "Approved Policies", (18, 36.8))
    draw_arrow(50, 40.5, 50, 33, C_L2_BORDER, '->', 1.2, "Masks / Rules", (50, 36.8))
    draw_arrow(82, 40.5, 82, 33, C_L2_BORDER, '->', 1.2, "Noise / Revoke", (82, 36.8))


    # 3. LAYER 3: CRYPTOGRAPHIC & AGGREGATION EXECUTION ENGINE (LOWER ROW)
    draw_card(2, 17, 96, 16, C_L3_BG, C_L3_BORDER, "Cryptographic Execution & Robust Aggregation Layer (Flower Integration)", C_L3_TEXT)

    draw_subbox(4, 19, 28, 11, C_L3_BOX, C_L3_BORDER, [
        ("Modular Tensor Quantizer", 8.5, 'bold'),
        ("R_scale = 2^16, Modulus R = 2^32-1", 7.5, 'normal'),
        ("y_u = x^~_u + Σ PRG(s_u,v) (mod R)", 7.0, 'bold')
    ], C_L3_TEXT)

    draw_subbox(36, 19, 28, 11, C_L3_BOX, C_L3_BORDER, [
        ("Byzantine Robust Aggregators", 8.5, 'bold'),
        ("Trimmed Mean (β=0.2), Median", 7.5, 'normal'),
        ("Krum Distance Filtering", 7.5, 'normal')
    ], C_L3_TEXT)

    draw_subbox(68, 19, 28, 11, C_L3_BOX, C_L3_BORDER, [
        ("Global Model Orchestration", 8.5, 'bold'),
        ("Aggregated Update Δ_global", 7.5, 'normal'),
        ("Flower FL Engine Integration", 7.5, 'normal')
    ], C_L3_TEXT)

    # Arrows inside Layer 3
    draw_arrow(32, 24.5, 36, 24.5, C_L3_BORDER, '->', 1.0)
    draw_arrow(64, 24.5, 68, 24.5, C_L3_BORDER, '->', 1.0)


    # 4. LAYER 4: TAMPER-EVIDENT AUDIT LEDGER & MACHINE UNLEARNING (BOTTOM ROW)
    draw_card(2, 1, 96, 13, C_L4_BG, C_L4_BORDER, "Immutable Storage & Verification Layer", C_L4_TEXT)

    draw_subbox(4, 2.5, 44, 9, C_L4_BOX, C_L4_BORDER, [
        ("SHA-256 Hash-Chained Audit Ledger", 8.5, 'bold'),
        ("H_k = SHA-256( H_(k-1) || E_k || T_UTC || Sign_server )  —  Tamper-Evident Event Verification", 7.2, 'normal')
    ], C_L4_TEXT)

    draw_subbox(52, 2.5, 44, 9, C_L4_BOX, C_L4_BORDER, [
        ("GDPR Art. 17 Machine Unlearning Checkpoint Store", 8.5, 'bold'),
        ("FedEraser Checkpoint Purification & Parameter Reconstruction on Client Eviction", 7.2, 'normal')
    ], C_L4_TEXT)

    # Arrows from Layer 2/3 to Layer 4
    draw_arrow(26, 17, 26, 11.5, C_L4_BORDER, '->', 1.2, "Log Audit Events", (26, 14.2))
    draw_arrow(74, 17, 74, 11.5, C_L4_BORDER, '->', 1.2, "Purify Checkpoints", (74, 14.2))

    plt.tight_layout()
    plt.savefig(OUTPUT_PATH, format='pdf', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[SUCCESS] Architecture diagram successfully rendered and saved to: {OUTPUT_PATH}")

if __name__ == "__main__":
    create_architecture_diagram()
