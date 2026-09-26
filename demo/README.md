# TestQ Demo Store

A minimal e-commerce demo application designed for Hackathon verification of TestQ's end-to-end automated testing, discovery, test generation, and failure analysis pipeline.

## Routes & Pages

- `/` — Store Home
- `/products` — Product Catalog
- `/login` — User Authentication
- `/cart` — Shopping Cart
- `/checkout` — Order Checkout
- `/api/status` — Health Check
- `/api/products` — Product List API
- `/api/login` — Authentication API
- `/api/checkout` — Order Placement API

## Intentional Defects

1. **BUG-001 (Validation):** Checkout accepts order with `quantity: 0` without error.
2. **BUG-002 (Validation / Auth):** Login accepts invalid email formats without RFC/regex validation.
3. **BUG-003 (Navigation):** Cart "Proceed to Checkout" button navigates to broken route `/checkout-broken` (HTTP 404).
