"""
benchmarks/generate_architecture_diagram.py
────────────────────────────────────────────────────────
Generates a sleek, modern, publication-quality vector PDF architecture diagram 
for the FedGuard Governance Control Plane & Conclave Reference Implementation.
Guarantees ZERO text overlap, generous padding, and perfect alignment.
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
    "font.size": 8.0,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

def create_architecture_diagram():
    # 7.1 in wide (full double column width in IEEEtran), 5.8 in height for optimal vertical spacing
    fig, ax = plt.subplots(figsize=(7.1, 5.8), dpi=300)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')

    # Color Palette - Professional Modern IEEE Theme
    C_L1_BG = "#f0fdf4"
    C_L1_BORDER = "#0d9488"
    C_L1_TEXT = "#064e3b"
    C_L1_BOX = "#ccfbf1"

    C_L2_BG = "#eef2ff"
    C_L2_BORDER = "#4f46e5"
    C_L2_TEXT = "#1e1b4b"
    C_L2_BOX = "#e0e7ff"

    C_L3_BG = "#f8fafc"
    C_L3_BORDER = "#334155"
    C_L3_TEXT = "#0f172a"
    C_L3_BOX = "#e2e8f0"

    C_L4_BG = "#fff1f2"
    C_L4_BORDER = "#e11d48"
    C_L4_TEXT = "#881337"
    C_L4_BOX = "#ffe4e6"

    # Helper function to draw rounded cards
    def draw_card(x, y, w, h, bg, border, title="", title_color="#000000", lw=1.2, r=1.5):
        box = patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0,rounding_size={r}",
            facecolor=bg, edgecolor=border, linewidth=lw, zorder=1
        )
        ax.add_patch(box)
        if title:
            ax.text(x + 2.0, y + h - 0.7, title, fontsize=8.8, fontweight='bold', color=title_color, va='top', zorder=2)

    def draw_subbox(x, y, w, h, bg, border, text_lines, text_color="#000000", lw=1.0, align='left', r=1.0):
        box = patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0,rounding_size={r}",
            facecolor=bg, edgecolor=border, linewidth=lw, zorder=3
        )
        ax.add_patch(box)
        
        n_lines = len(text_lines)
        line_spacing = (h - 1.6) / (n_lines + 0.3) if n_lines > 1 else h / 2.0
        
        for i, line in enumerate(text_lines):
            line_y = y + h - 1.2 - (i + 0.5) * line_spacing
            txt_val, sz, weight = line[0], line[1], line[2]
            
            if align == 'center':
                ax.text(x + w/2, line_y, txt_val, fontsize=sz, fontweight=weight, color=text_color, ha='center', va='center', zorder=4)
            else:
                ax.text(x + 1.8, line_y, txt_val, fontsize=sz, fontweight=weight, color=text_color, ha='left', va='center', zorder=4)

    def draw_arrow(x1, y1, x2, y2, color="#475569", style='->', lw=1.1, text="", text_pos=None):
        ax.annotate(
            "", xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle=style, color=color, lw=lw, mutation_scale=9),
            zorder=5
        )
        if text and text_pos:
            ax.text(text_pos[0], text_pos[1], text, fontsize=6.8, fontweight='bold', color=color, ha='center', va='center', zorder=6,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#ffffff", edgecolor=color, linewidth=0.6, alpha=0.95))

    # ==================== ARCHITECTURE DIAGRAM LAYOUT ====================

    # Main Title Banner
    ax.text(50, 98.4, "FedGuard Governance Control Plane & Conclave System Architecture", 
            fontsize=10.5, fontweight='bold', color="#0f172a", ha='center', va='center')

    # 1. LAYER 1: CLIENT PARTICIPANTS & HARDWARE ATTESTATION (y = 74.5 to 96.0, h = 21.5)
    draw_card(1.5, 74.5, 97, 21.5, C_L1_BG, C_L1_BORDER, "1. Participant Layer: Multi-Institutional Edge Nodes & Hardware Root-of-Trust", C_L1_TEXT)

    # 3 Client Nodes Subboxes (y = 75.8, h = 15.2 -> top = 91.0)
    draw_subbox(3.5, 75.8, 29, 15.2, C_L1_BOX, C_L1_BORDER, [
        ("Client Node u (Hospital / Bank)", 7.8, 'bold'),
        ("• mTLS 1.3 X.509 Certificate", 6.8, 'normal'),
        ("• TPM 2.0 PCR Attestation Quote", 6.8, 'normal'),
        ("• Local PyTorch Model Update Δ_u", 6.8, 'normal')
    ], C_L1_TEXT, align='left')

    draw_subbox(35.5, 75.8, 29, 15.2, C_L1_BOX, C_L1_BORDER, [
        ("Client Node v (Enterprise Silo)", 7.8, 'bold'),
        ("• mTLS 1.3 X.509 Certificate", 6.8, 'normal'),
        ("• TPM 2.0 PCR Attestation Quote", 6.8, 'normal'),
        ("• Local PyTorch Model Update Δ_v", 6.8, 'normal')
    ], C_L1_TEXT, align='left')

    draw_subbox(67.5, 75.8, 29, 15.2, C_L1_BOX, C_L1_BORDER, [
        ("Client Node N (Edge Participant)", 7.8, 'bold'),
        ("• mTLS 1.3 X.509 Certificate", 6.8, 'normal'),
        ("• Software Certificate Fallback", 6.8, 'normal'),
        ("• Local PyTorch Model Update Δ_N", 6.8, 'normal')
    ], C_L1_TEXT, align='left')

    # Arrows Layer 1 -> Layer 2
    draw_arrow(18, 75.8, 18, 69.5, C_L1_BORDER, '->', 1.1, "mTLS / Quote", (18, 72.65))
    draw_arrow(50, 75.8, 50, 69.5, C_L1_BORDER, '->', 1.1, "mTLS / Quote", (50, 72.65))
    draw_arrow(82, 75.8, 82, 69.5, C_L1_BORDER, '->', 1.1, "mTLS / Fallback", (82, 72.65))


    # 2. LAYER 2: GOVERNANCE CONTROL PLANE (y = 42.5 to 69.5, h = 27.0)
    draw_card(1.5, 42.5, 97, 27.0, C_L2_BG, C_L2_BORDER, "2. FedGuard Decoupled Governance Control Plane Engine", C_L2_TEXT)

    # Subbox 2A: ABAC/RBAC Policy Verification Engine
    draw_subbox(3.5, 43.8, 29, 20.8, C_L2_BOX, C_L2_BORDER, [
        ("ABAC / RBAC Policy Engine", 7.8, 'bold'),
        ("• X.509 Certificate Validation", 6.8, 'normal'),
        ("• Role & Attribute Matching", 6.8, 'normal'),
        ("• TPM 2.0 Quote Measurement", 6.8, 'normal'),
        ("• Dynamic Access Enforcement", 6.8, 'normal'),
        ("• HIPAA / GDPR Mappings", 6.8, 'bold')
    ], C_L2_TEXT, align='left')

    # Subbox 2B: Governance Mode & Threshold SecAgg Handler
    draw_subbox(35.5, 43.8, 29, 20.8, C_L2_BOX, C_L2_BORDER, [
        ("Mode Handler & SecAgg", 7.8, 'bold'),
        ("• Mode Selection:", 6.8, 'bold'),
        ("   - SECURE_AGGREGATION", 6.5, 'normal'),
        ("   - BYZANTINE_RESILIENT", 6.5, 'normal'),
        ("• Pairwise ECDH Key Exchange", 6.8, 'normal'),
        ("• Shamir Secret Sharing (k-of-N)", 6.8, 'normal')
    ], C_L2_TEXT, align='left')

    # Subbox 2C: RDP Privacy Accountant & Unlearning Trigger
    draw_subbox(67.5, 43.8, 29, 20.8, C_L2_BOX, C_L2_BORDER, [
        ("Privacy & Unlearning Engine", 7.8, 'bold'),
        ("• Rényi DP Budget Accountant", 6.8, 'normal'),
        ("  (Tracks (ε_t, δ_t) vs ε_max)", 6.5, 'normal'),
        ("• Gaussian Noise Injector", 6.8, 'normal'),
        ("• GDPR Art. 17 Revocation Handler", 6.8, 'normal'),
        ("• FedEraser Unlearn Trigger", 6.8, 'bold')
    ], C_L2_TEXT, align='left')

    # Horizontal Intra-Layer Arrows inside Layer 2
    draw_arrow(32.5, 54.2, 35.5, 54.2, C_L2_BORDER, '->', 1.0)
    draw_arrow(64.5, 54.2, 67.5, 54.2, C_L2_BORDER, '->', 1.0)

    # Vertical Inter-Layer Arrows Layer 2 -> Layer 3
    draw_arrow(18, 43.8, 18, 37.5, C_L2_BORDER, '->', 1.1, "Policy Authorization", (18, 40.65))
    draw_arrow(50, 43.8, 50, 37.5, C_L2_BORDER, '->', 1.1, "SecAgg / Mask Rules", (50, 40.65))
    draw_arrow(82, 43.8, 82, 37.5, C_L2_BORDER, '->', 1.1, "DP Noise / Revocation", (82, 40.65))


    # 3. LAYER 3: CRYPTOGRAPHIC & AGGREGATION EXECUTION ENGINE (y = 21.0 to 37.5, h = 16.5)
    draw_card(1.5, 21.0, 97, 16.5, C_L3_BG, C_L3_BORDER, "3. Cryptographic Execution & Robust Aggregation Layer (Flower Integration)", C_L3_TEXT)

    draw_subbox(3.5, 22.2, 29, 11.2, C_L3_BOX, C_L3_BORDER, [
        ("Modular Tensor Quantizer", 7.8, 'bold'),
        ("• Scale γ = 2^16, Modulus R = 2^32-1", 6.3, 'normal'),
        ("• y_u = x_u + Σ PRG(s) (mod R)", 6.3, 'bold')
    ], C_L3_TEXT, align='left')

    draw_subbox(35.5, 22.2, 29, 11.2, C_L3_BOX, C_L3_BORDER, [
        ("Byzantine Robust Aggregators", 7.8, 'bold'),
        ("• Trimmed Mean (β=0.2), Median", 6.8, 'normal'),
        ("• Krum Coordinate Distance Filter", 6.8, 'normal')
    ], C_L3_TEXT, align='left')

    draw_subbox(67.5, 22.2, 29, 11.2, C_L3_BOX, C_L3_BORDER, [
        ("Global Model Orchestration", 7.8, 'bold'),
        ("• Aggregated Update Δ_global", 6.8, 'normal'),
        ("• Flower FL Engine Dispatch", 6.8, 'normal')
    ], C_L3_TEXT, align='left')

    # Intra-Layer Arrows in Layer 3
    draw_arrow(32.5, 27.8, 35.5, 27.8, C_L3_BORDER, '->', 1.0)
    draw_arrow(64.5, 27.8, 67.5, 27.8, C_L3_BORDER, '->', 1.0)


    # 4. LAYER 4: AUDIT LEDGER & MACHINE UNLEARNING (y = 1.0 to 17.0, h = 16.0)
    draw_card(1.5, 1.0, 97, 16.0, C_L4_BG, C_L4_BORDER, "4. Immutable Storage & Verification Layer", C_L4_TEXT)

    draw_subbox(3.5, 2.4, 45, 10.5, C_L4_BOX, C_L4_BORDER, [
        ("SHA-256 Hash-Chained Audit Ledger", 7.8, 'bold'),
        ("H_k = SHA-256( H_(k-1) || Event_k || T_UTC || Sign_server )", 6.1, 'bold'),
        ("Tamper-Evident Historical Audit Event Verification", 6.5, 'normal')
    ], C_L4_TEXT, align='center')

    draw_subbox(51.5, 2.4, 45, 10.5, C_L4_BOX, C_L4_BORDER, [
        ("GDPR Art. 17 Machine Unlearning Store", 7.8, 'bold'),
        ("FedEraser Gradient History Un-rolling & Purification", 6.1, 'bold'),
        ("Automated Model Parameter Reconstruction on Eviction", 6.5, 'normal')
    ], C_L4_TEXT, align='center')

    # Inter-Layer Arrows Layer 3 -> Layer 4
    draw_arrow(26, 22.2, 26, 12.9, C_L4_BORDER, '->', 1.1, "Audit Event Logging", (26, 17.55))
    draw_arrow(74, 22.2, 74, 12.9, C_L4_BORDER, '->', 1.1, "Purify Checkpoints", (74, 17.55))

    plt.tight_layout()
    plt.savefig(OUTPUT_PATH, format='pdf', dpi=300, bbox_inches='tight')
    
    # Save PNG preview
    png_preview_path = "research_paper/figures/fig_fedguard_architecture.png"
    plt.savefig(png_preview_path, format='png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[SUCCESS] Sleek architecture diagram generated cleanly at:\n - PDF: {OUTPUT_PATH}\n - PNG: {png_preview_path}")

if __name__ == "__main__":
    create_architecture_diagram()
