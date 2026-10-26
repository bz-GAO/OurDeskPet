"""RinaYaki live: a separate realtime runtime for streaming translation.

The live runtime is intentionally independent from the offline job model:
it runs its own capture/ASR/translation chain with bounded latency, and it
never blocks on refinement work. Recorded sessions stay in their own
directory and can later be promoted into a normal offline project.
"""
