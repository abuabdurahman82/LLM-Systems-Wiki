# Mixture-of-Experts (MoE) — Why AllToAll Is the Real Test
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: DeepSeek-V3 tech report (arXiv:2412.19437), research-workloads MoE analysis, section [E] constants bank; fetched 2026-08-25.

## 30-Second Explanation
A Mixture-of-Experts (MoE) model interleaves **sparse expert layers** with dense layers:
every token is routed ("dispatched") by a router to a **top-k** subset of experts, the
expert computes, and the results are gathered back ("combined"). The network consequence
is a **token-granular AllToAll** — the dense part of the model is an orderly AllReduce
train, but *each expert layer fires an all-to-all in a synchronized burst*, where **every
GPU sends tokens to the GPUs hosting the experts it needs**. Because AllToAll performs
**no reduction**, every byte is a distinct flow: there is no bandwidth amortization, so
the fabric is stressed far harder than by AllReduce, and three failure modes emerge —
**burstiness** (all-to-all fires in synchronized pulses), **incast at expert nodes**
(many senders converge on the node hosting a hot expert), and **skew** (uneven expert
popularity concentrates load on a few NICs [E]). This is why future AI networks must
optimize **AllToAll, not just AllReduce**, and why **rail-optimized fabrics** and
node-limited routing matter (DeepSeek bounds dispatch to a small node subset [F]). See
the dense-collective baseline in [./33-collective-communication.md](./33-collective-communication.md).

## Why MoE stresses networks differently
Dense transformers are **bandwidth-bound AllReduce** machines; MoE changes the *shape* of
the load [I]:
- **Dense layers** → one AllReduce over gradients per step (or per TP layer): steady,
  reducible, bandwidth-amortized.
- **Expert layers** → a **token routing (top-k dispatch)** that moves individual tokens to
  experts; then **AllToAll combine** back. This is **permutation, not reduction** — no
  `2(n-1)/n` savings; every token byte is a distinct flow across the fabric [I].

So an MoE model is *both* an AllReduce machine (dense part) *and* an AllToAll machine
(expert part) on the same fabric — the AllToAll is what new networks under-provision for.

## The all-to-all fanout
In expert parallelism, experts live on *other* GPUs/nodes. For every token, the router
picks up to `k` experts → the token is sent (dispatched) to those experts' hosts; results
combine back. At cluster scale:

```text
  Every GPU dispatches to the GPUs hosting its chosen experts
  (top-k routing ⇒ each GPU touches up to k remote expert hosts)

         GPU0 ─▶ GPU4 (expert E)     GPU0's tokens need experts on {GPU4, GPU7}
         GPU1 ─▶ GPU7 (expert E)     GPU1's tokens need experts on {GPU4, GPU6}
         GPU2 ─▶ GPU5 (expert E)     ...every GPU sends AND receives — all-to-all
         GPU3 ─▶ GPU6 (expert E)
         GPU4 ◀─ GPU0,GPU1,GPU5,... (tokens from many sources converge here = incast)
         ...
  One dispatch + one combine AllToAll per expert layer · no reduction · N flows × N sources
```

The fanout is over the **experts a token needs** (`k`), but because experts are spread
across nodes, the *effective* pattern is **every node → every node** — a genuine all-to-all
[I]. Expert placement is the lever:
- **Node-local experts** (as many experts as fit on the local node / local subset) keep
  dispatch on fast local links → low network cost [F: DeepSeek-V3 node-limited routing].
- **Spread experts** (one expert per GPU across the cluster) maximize expert parallelism
  and throughput but push every dispatch across the fabric → higher network cost [A].

## Burstiness vs steady AllReduce
AllReduce is a **steady stream**: every step moves a comparable gradient volume at a
comparably high rate. The MoE all-to-all is **bursty**: all GPUs fire their dispatch at
the *same instant* each expert layer (synchronized), then idle while experts compute, then
combine in another synchronized burst [I].

```text
  Dense AllReduce:   ████████████████████████████  steady, reducible
  MoE all-to-all:    ▄▄▄  ████   ▄▄▄  ████   ▄▄▄   synchronized bursts; every GPU
                     (dispatch)(experts) (combine)  fires at once → fabric micro-bursts
```

Because bursts are synchronized, they land as **micro-burst incast** — many flows converge
on a receiving NIC or spine in the same instant, far exceeding average rate — which is the
classic trigger for buffer pressure, ECN/CNP (./32), and tail latency [I].

## Incast at expert nodes & network skew
The receiving node's NIC sees **incast**: every other node dispatches tokens to it
simultaneously. And because AllToAll **does no reduction**, there is **no bandwidth
saving** — the inbound NIC must absorb the full concurrent dispatch volume [I].

**Uneven expert popularity → skew.** Real routers are load-imbalanced (top-k + soft
load-balancing losses), so some expert nodes absorb an outsized share [I]. With 1M tokens
and top-8 routing, the fabric carries 1M × 8 = 8M dispatch expert-slots; spread over 32
experts that is **250k slots/expert** in the uniform case [E: 8e6/32]. Skew then works like
this:

```
  Uniform baseline:  250k dispatch slots/expert  (1M tokens × top-8 ÷ 32 experts) [E]
  Skew: a hot expert absorbs a +20% share of GLOBAL routing
        = +0.20 × 1M = +200k tokens onto that one expert [E: 0.2×1e6]
        ⇒ +200k / 250k = **+80% on that expert** [E]
  At node level (4 experts/node, 1M dispatch arrivals/node uniform [E: 250k×4]):
        the same +200k = +20% relative on its NIC; if all 200k land on the single
        hottest expert, the NIC sees up to 1.2×–1.8× its fair-share burst [A]
```

(Roughly, redirecting 20% of *global* routing onto one hot expert is an 80% jump on that
expert's load — the classic `1/(1-s)`-style skew amplification. **The multiplier depends on
concentration** — spread the same 200k over the hot node's 4 experts and it dilutes to
~+20%/expert, +20% relative on the node [A].) The mechanism — not the specific number — is
the point: skew directly magnifies incast at the popular expert node.

## Load-balancing auxiliary loss — and its network effect
MoE training adds **load-balancing auxiliary loss** to nudge the router toward even expert
utilization (soft, not hard — it trades a little model quality for less imbalance) [F:
DeepSeek-V3 tech report; I]. The fabric consequence: a **better-balanced router means less
skew → less incast → shorter tails** at expert nodes [I]. So the selection of the router
loss term has a *network* effect, not just a quality one — two agencies pulling in the
same direction:
- **Balancing** keeps expert NICs from becoming single-point bottlenecks.
- But balancing cannot make AllToAll *reducing* — even a perfect router still fans out and
  fans in every token; only node-local placement cuts cross-node bytes (see above) [I].

## Why future AI networks must optimize AllToAll, not just AllReduce
MoE is now the dominant trade for scaling model capacity at fixed compute (DeepSeek-V3,
mixture-of-experts LLMs), and its signature is AllToAll [F: DeepSeek-V3]. The imperative
for fabrics [I]:
- **AllReduce is nearly solved**: ring gets to the bandwidth lower bound (./33); you
  cannot squeeze much more out of an AllReduce.
- **AllToAll is the unsolved, growing load**: token permutation, no reduction, bursty,
  incast-bound, skew-amplified. As expert counts and cluster sizes grow, the all-to-all
  (dispatch + combine) dominates the fabric's tail.
- **So: design the fabric (and congestion control, cooling of NIC headroom, telemetry) for
  the all-to-all, not the all-reduce.** This is the same conclusion Ultra Ethernet's
  spraying + receiver-credit CC and in-network collectives target (./31, ./32): an
  unordered, spraying, incast-optimized transport helps the all-to-all far more than it
  helps an already-optimal ring AllReduce [I].

## Implications for rail-optimized fabrics
A **rail** is a dedicated plane for one NIC per node (see ./42, topology pages). For MoE
[I/A]:
- **Expert parallelism wants the free rail-to-rail fabric.** Because any GPU may dispatch
  to any expert, **cross-rail traffic is the cost**; keeping an expert "shard" within a
  rail / set of rails (placement!) reduces cross-rail hops.
- **Incast is local to the expert node's rail**: oversubscribing the uplinks that feed
  expert nodes turns token bursts into drops. Rail count / oversubscription decisions
  should be made with the all-to-all skew in mind, not the all-reduce average [E intuition].
- **DeepSeek's node-limited routing (top-k restricted to a small node subset)** is exactly
  a *placement* knob that bounds cross-rail fanout — the fabric engineer should plan rail
  and placement *together* [F: node-limited routing; A: implication].

## Lab — hand-calculable check [E]
```
# Bank row: MoE skew mechanism (per-expert framing)
tokens = 1_000_000; experts = 32; top_k = 8
slots_total = tokens * top_k            # 8e6 dispatch expert-slots  [E: 1e6×8]
per_expert = slots_total // experts     # 250,000 slots/expert uniform  [E: 8e6/32]
# +20% of GLOBAL routing concentrated on one hot expert:
extra = 0.20 * tokens                   # 200,000 tokens   [E: 0.2×1e6]
amplification = extra / per_expert      # 0.8 => +80% on that expert  [E: 200k/250k]
print(f"uniform {per_expert}/expert; hot expert +{amplification:.0%}")
```
Then, on a real cluster, run `alltoall_perf` while an MoE job runs: *expect* AllToAll bus
throughput to collapse under the dispatch burst even when `all_reduce_perf` looked perfect
— that gap is the AllToAll-vs-AllReduce thesis in one measurement [A].

> **Where this fits.** The dense-collective baseline is [./33-collective-communication.md](./33-collective-communication.md);
> the congestion-control side of the incast is [./32-uetch-congestion-and-in-network.md](./32-uetch-congestion-and-in-network.md);
> training vs inference framing in [./35-training-vs-inference.md](./35-training-vs-inference.md);
> measurement in [./44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md).

## Key Takeaways
1. An MoE model is **both an AllReduce machine (dense part) and an AllToAll machine (expert part)** on the same fabric — the AllToAll is what new networks under-provision for. [I]
2. AllToAll performs **no reduction**, so every token is a distinct flow with no bandwidth amortization — it stresses the fabric far harder than AllReduce. [I]
3. Three failure modes: **burstiness** (synchronized dispatch/combine pulses → micro-burst incast), **incast at expert nodes** (all nodes converge on a hot expert's NIC), and **skew** (uneven expert popularity; a +20% global imbalance shows up as +80% on one node [E]). [I/E]
4. **Placement is the lever**: node-local experts keep dispatch on fast local links, and DeepSeek's **node-limited top-k routing** bounds cross-rail fanout — plan rail and placement together. [F]
5. Design the fabric for **AllToAll, not just AllReduce**: ring AllReduce is near the bandwidth lower bound and "solved," while all-to-all is incast-bound, skew-amplified, and growing with expert count — exactly what UET's spraying + receiver-credit CC and INC target. [I]

## Related
- [33-collective-communication.md](./33-collective-communication.md) — the dense-collective baseline and wire-traffic multipliers.
- [32-uetch-congestion-and-in-network.md](./32-uetch-congestion-and-in-network.md) — the congestion-control/in-network side of the incast.
- [35-training-vs-inference.md](./35-training-vs-inference.md) — training vs inference framing, incl. MoE-inference EP traffic.
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) — measuring AllToAll vs AllReduce (alltoall_perf).
- [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) — rail/topology context for placement decisions.
- [55-cheat-sheet.md](./55-cheat-sheet.md) — quick reference across the section.

## References
- DeepSeek-V3 tech report (arXiv:2412.19437) — node-limited routing, load-balancing auxiliary loss [F].
- research-workloads MoE analysis — burstiness/skew/incast mechanism [I].
- [E] AFN constants bank — "MoE skew" row (+20% → +80%, 32 experts / 8 nodes).
