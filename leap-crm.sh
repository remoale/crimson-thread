curl -X POST https://api.jobprogress.com/api/v3/prospects \
  -H "Content-Type: application/json" \
  -H "x-api-key: LEAP_API_KEY" \
  -d '{
        "firstName":   "Jane",
        "lastName":    "Doe",
        "phonePrimary":"555-123-4567",
        "email":       "jane.doe@example.com",
        "street1":     "123 Maple St",
        "city":        "Austin",
        "state":       "TX",
        "postalCode":  "78701",
        "tradeType":   "Roofing"
      }'
