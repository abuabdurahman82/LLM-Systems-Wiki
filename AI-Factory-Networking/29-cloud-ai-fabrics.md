# Cloud AI Fabrics: AWS EFA, Google TPU, Microsoft
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: AWS EFA/SRD docs + AWS 2019 OFA deck, Google TPU architecture/Cloud blog + HotChips, Microsoft "Inside Maia 100"/Maia 200 + NVIDIA Fairwater (Nov 2025); fetched 2026-08-25.

## 30-Second Explanation
When hyperscalers build an AI fabric, they **do not have to use the same ingredients as a
merchant fabric** — they can design the NIC, the wire protocol, the topology, and the switch
all at once because they control the product and the data center. The three big designs are
three different answers to the *same physics* (synchronous collective traffic, tail latency,
incast, multipathing):
- **AWS** built **EFA + SRD**, a custom reliable-datagram protocol (not RoCE) with built-in
  congestion control, OS-bypass, and per-packet multipathing — and made it extremely hard to
  move off AWS.
- **Google** built a **private, largely non-Ethernet** fabric: TPU's **ICI** scale-up torus
  plus **OCS optical circuit switches** for the scale-out slice graph (its own interconnect,
  not commodity RoCE).
- **Microsoft** is the **UEC-founder + forwarded** one: **Maia** accelerators over an
  Ethernet/UEC-aligned backend, **and** NVIDIA **Spectrum-X + MRC** at **Fairwater** — the
  clearest hyperscale mixing board of all.
The lesson for a handbook: cloud fabrics are **engineering choices under the same physics**,
and each trades portability for a tightly-coupled, provider-tuned design. None of the three
is a "better RoCEv2" — they are bespoke systems that *absorb* RoCE-style problems differently.

## The same physics, three answers
| Force on the fabric | AWS | Google | Microsoft |
|---|---|---|---|
| Sync collective incast | SRD incast-aware CC | ICI + OCS reconfig | Ethernet/UEC + MRC |
| Tail latency | OS-bypass, multi-path | torus locality + OCS | Spectrum-X + Fairwater |
| Multipathing | **per-packet** (SRD) | circuit-switch slices | MRC multi-plane |
| End-to-end CC | built into SRD | not RoCE (no DCQCN) | UEC/Spectrum-X TCC |
| Portability/blast radius | **AWS-only** | GCP-only | Azure (but UEC-open path) |

## AWS: EFA + SRD (the custom reliable-datagram fabric)
**What it is.** The **Elastic Fabric Adapter (EFA)** is a Nitro-based NIC; it exposes **SRD
(Scalable Reliable Datagram)**, a **custom protocol** with built-in congestion control,
OS-bypass, per-packet **multi-pathing**, and **out-of-order delivery (no head-of-line
blocking)**. [F: AWS docs]
**Key fact.** **SRD is NOT RoCEv2.** AWS explicitly built SRD *instead of* RoCEv2; it is a
proprietary reliable-datagram protocol for AWS's fabric. [F: AWS docs + AWS 2019 OFA deck]
It also powers **ENA Express** and EBS `io2 Block Express`, so the same protocol underlies
VM + storage networking, not just HPC/AI. [F: AWS docs]

```text
   GPU/CPU  ⇄  EFA-Nitro NIC  ⇄  SRD  ⇄  AWS fabric (multi-path, load-aware)
      SEND critical traffic ──────────►   (out-of-order; receiver reassembles)
```
**Congestion control.** SRD uses **multi-path + load-aware per-packet scheduling** with
**incast-aware congestion control**. The commonly-cited wire name is **"IAC3" (Incast-Aware
Congestion Control)** — but IAC3's exact on-wire protocol name is **UNVERIFIED** beyond AWS's
docs describing SRD as having congestion control; treat "IAC3" as shorthand/UNVERIFIED. [F/I]
**Generations.** Nitro v3→v6, EFA v1→v4. [F: AWS]
**Positioning.** Instance families **P4/P5/P5e/UltraClusters/P6** and S3 use it; **not portable
off AWS**. The "no commodity RoCE in the standard story" is accurate: **AWS's standard AI/HPC
scale-out has no RoCEv2 at the EFA path** — it is SRD. [F/I]
**AWS vs the merchant fabric.** AWS is the purest form of the "custom ends-up beats generic"
bet: it ships its own NIC, its own protocol, its own topology. The price is that nothing about
it transfers to an on-prem cluster. [I: synthesis]

## Google: TPU fabric (ICI + OCS) — largely custom, lightly Ethernet
**What it is.** TPU scale-up interconnect is **ICI (Inter-Chip Interconnect)**, a proprietary
3D-torus link: TPU v4/v5 = **3D torus, 6 links/chip**; v5p = **4,800 Gb/s per chip** across six
links. [F: Google] Scale-out beyond the pod uses **OCS — Optical Circuit Switches** (MEMS
mirrors, ~10 s reconfig) to rewire which chips are connected, plus the **Jupiter** DC fabric
(custom silicon). [F]

```text
   TPU pod:  v4 = 4,096 chips;  v5p superpod = 8,960 chips, 48 OCS, ~4 Pb/s agg  [F: Google]
        ┌──────────────┐
        │ TPU (torus)  │ ← ICI (scale-up, proprietary, 6 links)
        └──────┬───────┘
     OCS optical circuit switch (scale-out reconfig, ~10 s)
        │  (TPU 8i: 36 groups / 1,024 chips via OCS, ≤7 hops [A/F: Google Cloud blog])
```
**Iridium / OCS context.** Google's "**Iridium**" optical-circuit-switching work is the broader
project of which TPU OCS is a deployment; the **specifics of Iridium-as-deployed for TPU are
treated as [I] UNVERIFIED here** because the research notes confirm the OCS numbers (v5p, 8,960
chips, ~4 Pb/s) but not a separately-named "Iridium" TPU product. [I/UNVERIFIED]
**The point.** Google uses **custom interconnect + circuit switching**, **not commodity RoCE**,
for AI scale-out — a deliberately bespoke topology that trades flexibility for dense, low-hops
connectivity. Treat **any specific custom-interconnect scale/protocol number not carried in the
notes as [I] UNVERIFIED**. [I]
**Best-fit.** TPU + Gemini workloads **on GCP only**; nothing is portable. [F/I]

## Microsoft: Maia + UEC + Spectrum-X (the mixing board)
**Maia.** **Maia 100** (custom accelerator) uses an **Ethernet-based backend interconnect** for
both scale-up and unified scale-out (direct + switch connectivity), running a **custom
RoCE-like protocol** with enhanced reliability/balance and **AES-GCM encryption**
(confidential-compute ready). [F: Microsoft TechCommunity HotChips 2024] **Maia 200**
(inference accelerator) announced Jan 2026. [A: Microsoft]
```text
   Azure AI
     ├── Maia 100/200  ── Ethernet backend (custom RoCE-like, AES-GCM)  [F]
     ├── UEC path      ── Microsoft co-founded/leads UEC ⇒ Azure is a key UEC impl [F]
     └── NVIDIA Spectrum-X + MRC at Fairwater (hundreds of k Blackwell GPUs) [F: NVIDIA/Microsoft Nov 2025]
```
**Fairwater + Spectrum-X.** Microsoft's **Fairwater** AI datacenter deploys **NVIDIA
Spectrum-X with MRC** (per NVIDIA-Microsoft, Nov 2025) — and **OpenAI's MRC deployment runs on
Spectrum-X** (the OpenAI "Resilient AI Supercomputer Networking using MRC and SRv6" story). [F/A]
So Azure hosts *both* Maia's custom RoCE-like Ethernet **and** NVIDIA's Spectrum-X/MRC, plus the
UEC path it leads — the pragmatic, multi-standard hyperscale answer. [F/I]
**Azure DPU.** **Azure Boost** (FPGA + in-house DPU ASIC, 200G) handles VM front-end networking.
[F: SemiAnalysis] Whether core training backends are "SONiC + Spectrum-4" specifically is
**UNVERIFIED/partial**: Spectrum-X is confirmed at Fairwater; SONiC may co-exist in
storage/front-end, not confirmed for training backends. [I]
**Why it matters.** Microsoft is the clearest demonstration that a hyperscaler does **not pick
one winner**: it runs its own silicon, the open UEC path it founded, and a competitive
proprietary fabric (Spectrum-X) depending on the workload. [I: synthesis]

## Cloud vs merchant fabrics, head-to-head
| Dimension | AWS EFA/SRD | Google TPU (ICI+OCS) | Microsoft (Maia+UEC+Spectrum-X) | Merchant (TH5/Etherlink/Nexus) |
|---|---|---|---|---|
| NIC/protocol | custom SRD (not RoCE) | custom ICI | custom RoCE-like + Spectrum-X | standard RoCEv2/UET (future) |
| Topology | AWS fabric, multi-path | 3D torus + OCS circuits | leaf-spine + MRC multi-plane | two-tier Clos, rail planes |
| Portability | none (AWS) | none (GCP) | little off Azure (UEC path open) | **full** (open hardware) |
| CC | SRD built-in (incast-aware) | not RoCE (OCS/torus) | UEC/Spectrum-X TCC | DCQCN now; UEC next |
| Fit | AWS HPC/AI at scale | TPU/Gemini on GCP | Azure mix, Fairwater | on-prem, multi-vendor |

## The engineering-lesson framing
All three are **engineering choices under the same physics** — synchronous collectives,
tail-latency dominance, incast, the multipathing/reliability tension. The hyperscalers'
answer is to **own more of the stack**: AWS owns NIC+protocol, Google owns NIC+topology+switch,
Microsoft owns accelerator+NOS+stands across three standards. The merchant fabric's answer is
**open commodity standard parts** so a *buyer*, not a provider, owns the stack. Neither is
"better" — they optimize different constraints (portability + ecosystem vs tight coupling +
provider tuning). [I: synthesis]

## Scale — a caution
**No product-scale numbers are fabricated here.** Where a count appears it is [F: vendor
primary] (e.g., Maia 100 feature set, TPU v5p superpod 8,960 chips, Fairwater "hundreds of
thousands of GPUs" per NVIDIA-Microsoft), or explicitly [I]/UNVERIFIED otherwise.
Heard-in-passing numbers (xAI/Colossus 100k, "Azure AI40000", "Iridium" TPU scale) are
**UNVERIFIED** and deliberately excluded. [I]
> A working rule for reading any cloud-fabric claim: **the provider owns every layer**, so a
> number quoted in a vendor deck is a *design target of a closed system*, not a spec of an
> open standard — verify against a primary source before carrying it into a design. [I]

## Concrete design lesson from each
- **AWS**: if you can own the NIC + protocol, you can have **per-packet multipathing and
  out-of-order delivery as free properties** of the fabric, not an engineering overlay — the
  single most instructive difference vs RoCEv2's one-hash-path limit ([22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)). [I]
- **Google**: **topology is itself a tunable**, and with OCS you can *rewire* it in ~10 s — a
  radically different lever than fixed tier counts ([42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)). The cost is
  that the fabric is purpose-shaped for TPU, not general-purpose. [I]
- **Microsoft**: **no single winner is required** — run custom silicon + the open standard you
  co-founded + a competitor's fabric in the same cloud, and route workloads to the best fit
  ([25-nvidia-spectrum-x.md](./25-nvidia-spectrum-x.md)). This is the pragmatic hyperscale answer and the closest to what
  a merchant-fabric buyer does. [I]

## Cloud vs on-prem: when each wins
| Constraint | Cloud fabric (EFA/TPU/Maia) | On-prem merchant fabric (TH5/Etherlink) |
|---|---|---|
| Time to large cluster | fast (provider-managed) | long (you build it) |
| Topology control | provider decides (rails/circuits) | **you decide** (rail, Clos, planes) |
| Tuning access | limited (black-box CC) | **full** (EOS/Junos/SONiC, DCQCN knobs) |
| Vendor coupling | extreme (single provider) | low (multi-vendor, open) |
| Best fit | burst/elastic, GCP/AWS/Azure-native | sustained on-prem training, multi-vendor |

The decision is rarely "which is technically better" — it is **which constraint (portability
vs provider tuning) you can tolerate**. [I] · decision framework: [49-design-decision-tree.md](./49-design-decision-tree.md).

## Key Takeaways
1. Cloud AI fabrics are **bespoke systems that absorb RoCE-style problems differently**, not
   "better RoCEv2." [I]
2. AWS = **SRD, not RoCE** — custom reliable-datagram, incast-aware CC, per-packet multipath,
   AWS-only. [F]
3. Google = **ICI torus + OCS circuit switching** — largely custom and non-Ethernet; Iridium
   specifics [I] UNVERIFIED. [F/I]
4. Microsoft = **biggest mixing board** — Maia (custom Ethernet), UEC (it founded), and
   Spectrum-X/MRC at Fairwater (OpenAI MRC). [F/A]
5. Trade-off axis: **portability/ecosystem (merchant) vs tight coupling/provider tuning
   (cloud)**. [I: synthesis]

## Related
- [26-arista-etherlink.md](./26-arista-etherlink.md) / [27-cisco-ai-ethernet.md](./27-cisco-ai-ethernet.md) — the merchant fabrics to compare
  against.
- [24-vendor-landscape.md](./24-vendor-landscape.md) — the full vendor map includes these.
- [25-nvidia-spectrum-x.md](./25-nvidia-spectrum-x.md) — Spectrum-X/MRC, the Fairwater enabler.
- [30-ultra-ethernet-consortium.md](./30-ultra-ethernet-consortium.md) — the UEC path Microsoft leads.
- [README.md](../Networking/README.md) — the one-page networking primer.

## References
- AWS: EFA + ENA Express docs, AWS 2019 OFA EFA/SRD deck [F: AWS]. IAC3 exact-on-wire name
  UNVERIFIED.
- Google: TPU architecture/Cloud blog + HotChips (v5p OCS numbers) [F]; Iridium-specific TPU
  deployment [I/UNVERIFIED].
- Microsoft: "Inside Maia 100" HotChips 2024 [F], Maia 200 blog (Jan 2026) [A], NVIDIA-Microsoft
  Fairwater (Nov 2025) [F], SemiAnalysis Azure Boost [F secondary].
- [E] constants where applied from the section bank (computed 2026-08-25).
