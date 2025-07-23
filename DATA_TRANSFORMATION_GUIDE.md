# Data Transformation System Guide

## Overview
This system allows frontend applications to post data that gets automatically transformed based on client-specific formats using templates.

## System Flow
```
Frontend POST → /ingest → Raw Data Storage → Background Job → Transform → Processed Data
```

## API Endpoints

### 1. Template Management

#### Create Template
```http
POST /templates
Content-Type: application/json

{
  "client_id": "ecommerce_client",
  "mapping": {
    "customer_name": "user_name",
    "customer_email": "user_email",
    "order_amount": "total_price",
    "product_count": "item_quantity"
  }
}
```

#### Get All Templates
```http
GET /templates
```

#### Get Template by Client ID
```http
GET /templates/ecommerce_client
```

#### Update Template
```http
PUT /templates/ecommerce_client
Content-Type: application/json

{
  "mapping": {
    "customer_name": "user_name",
    "customer_email": "user_email",
    "order_amount": "total_price"
  }
}
```

### 2. Data Ingestion

#### Post Raw Data
```http
POST /ingest
Content-Type: application/json

{
  "client_id": "ecommerce_client",
  "payload": {
    "user_name": "John Smith",
    "user_email": "john@example.com",
    "total_price": 299.99,
    "item_quantity": 3,
    "order_date": "2024-01-15"
  }
}
```

### 3. Manual Transformation (Optional)

#### Transform Data Immediately
```http
POST /transform
Content-Type: application/json

{
  "client_id": "ecommerce_client",
  "raw_data": {
    "user_name": "John Smith",
    "user_email": "john@example.com",
    "total_price": 299.99,
    "item_quantity": 3
  }
}
```

**Response:**
```json
{
  "transformed_data": {
    "customer_name": "John Smith",
    "customer_email": "john@example.com",
    "order_amount": 299.99,
    "product_count": 3
  }
}
```

## Example Use Cases

### Use Case 1: E-commerce Client
**Template:**
```json
{
  "client_id": "shopify_store_123",
  "mapping": {
    "customer_name": "buyer_name",
    "customer_email": "buyer_email",
    "order_total": "purchase_amount",
    "items_count": "product_quantity"
  }
}
```

**Input Data:**
```json
{
  "client_id": "shopify_store_123",
  "payload": {
    "buyer_name": "Alice Johnson",
    "buyer_email": "alice@email.com",
    "purchase_amount": 150.75,
    "product_quantity": 2,
    "store_location": "New York"
  }
}
```

**Transformed Output:**
```json
{
  "customer_name": "Alice Johnson",
  "customer_email": "alice@email.com",
  "order_total": 150.75,
  "items_count": 2
}
```

### Use Case 2: CRM Client
**Template:**
```json
{
  "client_id": "crm_system_456",
  "mapping": {
    "lead_name": "contact_name",
    "lead_email": "contact_email",
    "lead_phone": "contact_phone",
    "lead_source": "acquisition_channel"
  }
}
```

## Background Processing

The system automatically processes unprocessed data every **10 seconds** using a background job:

1. Finds all records with `processed = false`
2. Looks up the transformation template for each client_id
3. Applies the transformation mapping
4. Marks records as `processed = true`

## Error Handling

- **Missing Template**: If no template exists for a client_id, the record is skipped with a warning
- **Missing Fields**: If required fields are missing from raw data, transformation fails with an error
- **Invalid Data**: Malformed JSON or invalid data types are logged and skipped

## Database Tables

### `raw_data` Table
- `id`: Primary key
- `client_id`: Client identifier
- `payload`: JSON data from frontend
- `processed`: Boolean flag for processing status

### `templates` Table
- `id`: Primary key
- `client_id`: Client identifier (unique)
- `mapping`: JSON object defining field transformations

## Getting Started

1. **Create a template** for your client:
   ```bash
   curl -X POST "http://localhost:8000/templates" \
   -H "Content-Type: application/json" \
   -d '{
     "client_id": "my_client",
     "mapping": {
       "output_field": "input_field"
     }
   }'
   ```

2. **Post data from frontend**:
   ```bash
   curl -X POST "http://localhost:8000/ingest" \
   -H "Content-Type: application/json" \
   -d '{
     "client_id": "my_client",
     "payload": {
       "input_field": "some_value"
     }
   }'
   ```

3. **Data will be automatically transformed** within 10 seconds by the background job.

## Monitoring

Check the application logs to monitor:
- Data ingestion success/failures
- Transformation job execution
- Template lookup results
- Processing statistics