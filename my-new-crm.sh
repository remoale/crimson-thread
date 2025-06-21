curl -i -v \
  https://webhook.site/f366c4e1-bb35-49cb-986c-6a7b54ec1a7f \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
        "firstName": "Jane",
        "lastName":  "Doe",
        "email":     "jane.doe@example.com",
        "phone":     "+1-555-123-4567",
        "company":   "Acme Inc.",
        "createdAt": "2025-06-21T14:32:00Z"
      }'
