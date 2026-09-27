# Deliverable 4: agent transcripts via POST /ask-logistics
Captured 2026-09-27T19:16:11+00:00 against http://127.0.0.1:8001 (gpt-4o-mini, temperature 0, recursion_limit 8). Answers are verbatim.

## A. Multi-tool answer (coordinator)

**Request** `POST /ask-logistics` as `mercy`, HTTP **200**

> Which clinics need an amoxicillin reorder, and what route should the driver take from Kisumu Central?

**Answer**

```text
The clinics that need an amoxicillin reorder are:

1. **Vihiga Health Post** - 8 units (reorder needed)
2. **Homa Bay Lakeside Clinic** - 0 units (reorder needed)

The recommended delivery route from **Kisumu Central Clinic** is as follows:

1. **Kisumu Central Clinic** (0.0 km)
2. **Kisumu West Dispensary** (8.8 km)
3. **Vihiga Health Post** (17.5 km)
4. **Homa Bay Lakeside Clinic** (70.4 km)
5. **Kisii Family Clinic** (38.4 km)

**Total distance:** 135.1 km. This route is based on the nearest-neighbour heuristic on straight-line distance.
```

tools_used=['check_stock', 'plan_delivery_route'] model_calls=2 tokens_in=2148 tokens_out=219 trace_id=`535e141b`

**Trace** `grep "trace=535e141b" logs/*.log`

```text
agent.log: 2026-09-27 22:16:12,499 INFO agent trace=535e141b agent_start role=coordinator tools=['check_stock', 'get_delivery_eta', 'plan_delivery_route']
mcp_server.log: 2026-09-27 22:16:13,858 INFO logistics_mcp trace=535e141b tool=check_stock item='amoxicillin' county='None' outcome=ok ms=0
mcp_server.log: 2026-09-27 22:16:13,859 INFO logistics_mcp trace=535e141b tool=plan_delivery_route start_clinic_id='C01' stop_clinic_ids='None' outcome=ok ms=0
agent.log: 2026-09-27 22:16:15,827 INFO agent trace=535e141b step=1 tool_call=check_stock args={"item": "amoxicillin"}
agent_api.log: 2026-09-27 22:16:15,828 INFO agent_api trace=535e141b user=mercy role=coordinator outcome=answered ms=4068 question_chars=101 model_calls=2 tokens_in=2148 tokens_out=219 tools=check_stock,plan_delivery_route
agent_api.log: 2026-09-27 22:16:15,828 INFO agent_api trace=535e141b method=POST path=/ask-logistics status=200 ms=4070
agent.log: 2026-09-27 22:16:15,828 INFO agent trace=535e141b step=2 tool_call=plan_delivery_route args={"start_clinic_id": "C01"}
agent.log: 2026-09-27 22:16:15,828 INFO agent trace=535e141b agent_end status=answered model_calls=2 tokens_in=2148 tokens_out=219
```

## B. Honest failure: the data cannot answer this

**Request** `POST /ask-logistics` as `mercy`, HTTP **200**

> What is the price of amoxicillin at each clinic?

**Answer**

```text
I do not have access to pricing information for amoxicillin or any other medical items. However, I can provide you with the stock levels of amoxicillin at each clinic. Would you like that information?
```

tools_used=[] model_calls=1 tokens_in=834 tokens_out=43 trace_id=`f3c392d8`

**Trace** `grep "trace=f3c392d8" logs/*.log`

```text
agent.log: 2026-09-27 22:16:16,719 INFO agent trace=f3c392d8 agent_start role=coordinator tools=['check_stock', 'get_delivery_eta', 'plan_delivery_route']
agent_api.log: 2026-09-27 22:16:17,895 INFO agent_api trace=f3c392d8 user=mercy role=coordinator outcome=answered ms=1791 question_chars=48 model_calls=1 tokens_in=834 tokens_out=43 tools=
agent.log: 2026-09-27 22:16:17,895 INFO agent trace=f3c392d8 agent_end status=answered model_calls=1 tokens_in=834 tokens_out=43
agent_api.log: 2026-09-27 22:16:17,896 INFO agent_api trace=f3c392d8 method=POST path=/ask-logistics status=200 ms=1792
```

## C. Multi-step reasoning across three tools (coordinator)

**Request** `POST /ask-logistics` as `mercy`, HTTP **200**

> Homa Bay Lakeside has run out of amoxicillin. Which clinic holds the most amoxicillin, and how long would a delivery from that clinic to Homa Bay take?

**Answer**

```text
The clinic holding the most amoxicillin is **Kisii Family Clinic** with **75 units** on hand. A delivery from Kisii Family Clinic to **Homa Bay Lakeside Clinic** would take approximately **60 minutes**, covering a distance of **38.4 km**.
```

tools_used=['check_stock', 'get_delivery_eta'] model_calls=3 tokens_in=3169 tokens_out=102 trace_id=`d27375fd`

**Trace** `grep "trace=d27375fd" logs/*.log`

```text
agent.log: 2026-09-27 22:16:18,750 INFO agent trace=d27375fd agent_start role=coordinator tools=['check_stock', 'get_delivery_eta', 'plan_delivery_route']
mcp_server.log: 2026-09-27 22:16:19,708 INFO logistics_mcp trace=d27375fd tool=check_stock item='amoxicillin' county='None' outcome=ok ms=0
mcp_server.log: 2026-09-27 22:16:20,689 INFO logistics_mcp trace=d27375fd tool=get_delivery_eta from_clinic_id='C03' to_clinic_id='C04' outcome=ok ms=0
agent_api.log: 2026-09-27 22:16:21,893 INFO agent_api trace=d27375fd user=mercy role=coordinator outcome=answered ms=3755 question_chars=151 model_calls=3 tokens_in=3169 tokens_out=102 tools=check_stock,get_delivery_eta
agent_api.log: 2026-09-27 22:16:21,893 INFO agent_api trace=d27375fd method=POST path=/ask-logistics status=200 ms=3756
agent.log: 2026-09-27 22:16:21,893 INFO agent trace=d27375fd step=1 tool_call=check_stock args={"item": "amoxicillin"}
agent.log: 2026-09-27 22:16:21,893 INFO agent trace=d27375fd step=2 tool_call=get_delivery_eta args={"from_clinic_id": "C03", "to_clinic_id": "C04"}
agent.log: 2026-09-27 22:16:21,893 INFO agent trace=d27375fd agent_end status=answered model_calls=3 tokens_in=3169 tokens_out=102
```

## D. Honest partial answer: a place that is not a clinic

**Request** `POST /ask-logistics` as `mercy`, HTTP **200**

> How long does a delivery take from Kisumu Central Clinic to Kisumu International Airport?

**Answer**

```text
I cannot provide the delivery time from Kisumu Central Clinic to Kisumu International Airport as it is not a partner clinic. I can only provide information about the delivery times between partner clinics. If you have another route in mind, please let me know!
```

tools_used=[] model_calls=1 tokens_in=839 tokens_out=51 trace_id=`4ddd8f23`

**Trace** `grep "trace=4ddd8f23" logs/*.log`

```text
agent.log: 2026-09-27 22:16:22,752 INFO agent trace=4ddd8f23 agent_start role=coordinator tools=['check_stock', 'get_delivery_eta', 'plan_delivery_route']
agent_api.log: 2026-09-27 22:16:23,959 INFO agent_api trace=4ddd8f23 user=mercy role=coordinator outcome=answered ms=1808 question_chars=89 model_calls=1 tokens_in=839 tokens_out=51 tools=
agent_api.log: 2026-09-27 22:16:23,959 INFO agent_api trace=4ddd8f23 method=POST path=/ask-logistics status=200 ms=1809
agent.log: 2026-09-27 22:16:23,959 INFO agent trace=4ddd8f23 agent_end status=answered model_calls=1 tokens_in=839 tokens_out=51
```

## E. Permission rail: a viewer asks for a route

**Request** `POST /ask-logistics` as `guest`, HTTP **200**

> What route should the driver take from Kisumu Central to visit every clinic?

**Answer**

```text
I cannot provide route planning or delivery estimates as that requires a coordinator role. Please consult a logistics coordinator for assistance with route planning.
```

tools_used=[] model_calls=1 tokens_in=515 tokens_out=27 trace_id=`8d7a89e1`

**Trace** `grep "trace=8d7a89e1" logs/*.log`

```text
agent.log: 2026-09-27 22:16:24,807 INFO agent trace=8d7a89e1 agent_start role=viewer tools=['check_stock']
agent_api.log: 2026-09-27 22:16:25,884 INFO agent_api trace=8d7a89e1 user=guest role=viewer outcome=answered ms=1682 question_chars=76 model_calls=1 tokens_in=515 tokens_out=27 tools=
agent.log: 2026-09-27 22:16:25,884 INFO agent trace=8d7a89e1 agent_end status=answered model_calls=1 tokens_in=515 tokens_out=27
agent_api.log: 2026-09-27 22:16:25,885 INFO agent_api trace=8d7a89e1 method=POST path=/ask-logistics status=200 ms=1683
```

## F. No token

HTTP **401** `{"detail":"Not authenticated. Log in at /token and send 'Authorization: Bearer <token>'."}`

## G. Human-in-the-loop reorder: the agent recommends, a coordinator confirms

```text
propose as guest (viewer)                HTTP 201  {"id":"cf1596ee55d8","status":"proposed","clinic_id":"C04","item":"amoxicillin","units":50,"proposed_by":"guest","proposed_at":"2026-09-27T19:16:26+00:00","confirmed_by":null,"confirmed_at":null}
confirm as guest (viewer)                HTTP 403  {"detail":"Your role 'viewer' may not use this endpoint."}
confirm as mercy (coordinator)           HTTP 200  {"id":"cf1596ee55d8","status":"confirmed","clinic_id":"C04","item":"amoxicillin","units":50,"proposed_by":"guest","proposed_at":"2026-09-27T19:16:26+00:00","confirmed_by":"mercy","confirmed_at":"2026-09-27T19:16:26+00:00"}
confirm AGAIN as mercy (network retry)   HTTP 200  {"id":"cf1596ee55d8","status":"confirmed","clinic_id":"C04","item":"amoxicillin","units":50,"proposed_by":"guest","proposed_at":"2026-09-27T19:16:26+00:00","confirmed_by":"mercy","confirmed_at":"2026-09-27T19:16:26+00:00"}
```

## H. Guardrail comparison: question B with the system prompt removed

Tool docstrings still state that stock counts are units with no prices.

```text
I don't have access to pricing information for medical items like amoxicillin at the clinics. I can provide information on stock levels or help with other inquiries related to the clinics. Let me know if you need assistance with something else!
```

tools_used=[] model_calls=1

## Cost of this evidence run

tokens_in=8120 tokens_out=489, about $0.0015 at gpt-4o-mini list prices ($0.15 / $0.60 per million tokens).
