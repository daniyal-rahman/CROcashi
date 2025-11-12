# Match Candidate Review Results

**Date**: 2025-11-11 16:56:40  
**Reviewer**: automated_review  
**Status**: ✅ Complete

## Summary

- **Total Reviewed**: 31
- **Approved**: 11 (35.5%)
- **Rejected**: 20 (64.5%)
- **Errors**: 0
- **Aliases Created**: 10 (1 duplicate skipped)

## Review Process

All candidates were automatically reviewed using the following logic:

1. **High Confidence Matches (score ≥ 0.85)**: Automatically approved
2. **Medium Confidence Matches (0.70-0.84)**: 
   - Approved if extracted text matches entity name
   - Rejected if text doesn't match
3. **Low Confidence Matches (score < 0.70)**: Rejected (create new entity)
4. **No Matches**: Rejected (create new entity)
5. **Navigation/Header Text**: Rejected (not valid entity names)

## Results by Entity Type

- **Disease**: 20 candidates (8 approved, 12 rejected)
- **Institution**: 4 candidates (1 approved, 3 rejected)
- **Drug**: 1 candidate (0 approved, 1 rejected)
- **Regulatory Event**: 2 candidates (0 approved, 2 rejected)

## Results by Source

- **clinicaltrials_gov**: 28 candidates (10 approved, 18 rejected)
- **fda_guidance**: 2 candidates (0 approved, 2 rejected)
- **nih_reporter**: 1 candidate (1 approved, 0 rejected)

## Approved Matches

- **Candidate**: 88ae2aa8-3efd-45a3-9915-9cfd063920bf
  - **Matched to**: fad366aa-99e9-47c4-89db-d217535f186c
  - **Reasoning**: Medium confidence but text matches entity name (score: 0.71)

- **Candidate**: f8e73d95-7ff0-41c9-a8ec-4a65d1398e15
  - **Matched to**: fad366aa-99e9-47c4-89db-d217535f186c
  - **Reasoning**: Medium confidence but text matches entity name (score: 0.73)

- **Candidate**: 09fa5dcd-7ac8-4a3d-a857-bf5cbb630e00
  - **Matched to**: fad366aa-99e9-47c4-89db-d217535f186c
  - **Reasoning**: Medium confidence but text matches entity name (score: 0.75)

- **Candidate**: d976d3cc-39d5-405f-8ad9-f855c88f832a
  - **Matched to**: 70046c14-d995-4347-bedb-d62c2b8ca86f
  - **Reasoning**: Medium confidence but text matches entity name (score: 0.74)

- **Candidate**: 97bbd30f-8dbc-43ad-8285-13e21bbbdf33
  - **Matched to**: 335344b7-a0d0-4bd7-8fdf-38f07e95868a
  - **Reasoning**: Medium confidence but text matches entity name (score: 0.74)

- **Candidate**: c920048d-b27b-4bd4-a933-7ea5d6c79008
  - **Matched to**: 70046c14-d995-4347-bedb-d62c2b8ca86f
  - **Reasoning**: Medium confidence but text matches entity name (score: 0.74)

- **Candidate**: 1c24c88c-43c5-4cd8-992b-3b50b956c2ec
  - **Matched to**: 93a2e03b-bf68-44a5-a03d-b45ff1c2636e
  - **Reasoning**: Medium confidence but text matches entity name (score: 0.73)

- **Candidate**: 02e5be2d-4eda-443c-8381-3bd1ca6093c7
  - **Matched to**: 1e0ef7cc-ac27-40ff-990a-3d80c9bf4c2e
  - **Reasoning**: Medium confidence but text matches entity name (score: 0.70)

- **Candidate**: d3fea14c-7ef6-414b-9ac3-4d3677fbe266
  - **Matched to**: 634d30a6-33ae-4441-89ad-b4afb81d92ac
  - **Reasoning**: Medium confidence but text matches entity name (score: 0.81)

- **Candidate**: b1a28a2c-b3ef-4f70-92a2-327839a6622e
  - **Matched to**: 1c42fe4d-a01d-44a9-a229-a8b1f992be3c
  - **Reasoning**: Medium confidence but text matches entity name (score: 0.83)

- **Candidate**: ce0e36ba-324d-4784-9a23-fc6d605538b9
  - **Matched to**: 482f50a5-bf06-473b-8ff4-cdd13b3ab09d
  - **Reasoning**: Medium confidence but text matches entity name (score: 0.76)

## Rejected Matches (New Entities)

- **Candidate**: 509f652d-3a6b-484b-a190-1cd47a5ca9a2
  - **Reasoning**: Extracted text appears to be navigation/header text, not an entity name

- **Candidate**: 0b9551f5-f787-4d0b-9772-ce0670601523
  - **Reasoning**: Extracted text appears to be navigation/header text, not an entity name

- **Candidate**: ed405f58-00d6-4cc6-93b9-87f1753f5339
  - **Reasoning**: Extracted text appears to be navigation/header text, not an entity name

- **Candidate**: 412a3881-a7a2-4bd7-add9-a43c5750f49e
  - **Reasoning**: Extracted text appears to be navigation/header text, not an entity name

- **Candidate**: 5b2d0ff8-b5cd-4247-bec1-f64dd3213419
  - **Reasoning**: Medium confidence but text does not match (score: 0.74)

- **Candidate**: ff070544-2074-402f-9549-9be98aa0e695
  - **Reasoning**: Medium confidence but text does not match (score: 0.76)

- **Candidate**: 529c8055-87ee-423f-9cd7-afe72c420469
  - **Reasoning**: Medium confidence but text does not match (score: 0.82)

- **Candidate**: 964bceb1-9fe9-440a-81e1-5f4b3b372780
  - **Reasoning**: Multiple matches but best match has low confidence (score: 0.79) - create new entity

- **Candidate**: bd44a704-d275-4f3f-acfd-68eb11cd565e
  - **Reasoning**: Medium confidence but text does not match (score: 0.76)

- **Candidate**: ab549d28-5eea-4a96-939a-a45cdb2189fb
  - **Reasoning**: Medium confidence but text does not match (score: 0.77)

- **Candidate**: 4cbe1a3f-475f-4923-bb77-707abbab5e41
  - **Reasoning**: Medium confidence but text does not match (score: 0.74)

- **Candidate**: 6127ed80-1407-4742-b6ab-d48df77360f3
  - **Reasoning**: Multiple matches but best match has low confidence (score: 0.78) - create new entity

- **Candidate**: 98ce13a7-d131-4bd0-93aa-d6ffc8952b1f
  - **Reasoning**: Medium confidence but text does not match (score: 0.76)

- **Candidate**: 1f68022d-434e-4fd2-95e6-769cdf4a8800
  - **Reasoning**: Extracted text appears to be navigation/header text, not an entity name

- **Candidate**: 424ca2b8-cd35-4072-aa22-5bbbe9705054
  - **Reasoning**: Medium confidence but text does not match (score: 0.75)

- **Candidate**: 2fd80994-3cff-493a-8275-61d8bde12f97
  - **Reasoning**: Medium confidence but text does not match (score: 0.74)

- **Candidate**: 7ac8fcf6-5121-4dc4-90bf-727fcbd7411d
  - **Reasoning**: Medium confidence but text does not match (score: 0.73)

- **Candidate**: 3d593452-16eb-4bfd-b1fa-a9e59e2b1b7e
  - **Reasoning**: Multiple matches but best match has low confidence (score: 0.78) - create new entity

- **Candidate**: 20111bf7-9943-4005-bbd3-fe6890f9ab70
  - **Reasoning**: Extracted text appears to be navigation/header text, not an entity name

- **Candidate**: 1b3995b0-6df1-4283-a23c-960c5b9ca5e8
  - **Reasoning**: Extracted text appears to be navigation/header text, not an entity name

