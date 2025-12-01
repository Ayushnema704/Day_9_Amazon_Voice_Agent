# Amazon Voice Shopping Agent - Day 9

## Overview
This is an **Amazon Voice Shopping Assistant** built for Day 9 of the Murf AI Voice Agent Challenge. It demonstrates an ACP-inspired (Agentic Commerce Protocol) e-commerce voice agent that enables natural voice-based product discovery, cart management, and order placement.

## 🎯 Features Implemented

### ✅ Primary Goals (Required)
1. **Product Catalog Browsing** - Voice-enabled product search across multiple categories
2. **Natural Conversation** - Intelligent understanding of customer intent and context
3. **Shopping Cart Management** - Add, view, and remove items from cart
4. **Order Placement** - Complete checkout and generate order confirmations
5. **Order Persistence** - All orders saved to `amazon_orders.json`
6. **Order History** - View past purchases

### 📦 Product Catalog
**20 diverse products** across 5 categories:
- **Electronics**: Headphones, smartwatches, smart speakers, cameras
- **Books**: Bestsellers in self-help, finance, and science fiction
- **Fashion**: Jeans, sneakers, hoodies, accessories
- **Home & Kitchen**: Appliances, bedding, smart bulbs
- **Sports & Outdoors**: Football, gym accessories

All products include:
- Product ID, name, description
- Price in INR with currency
- Brand, color, ratings
- Stock availability
- Detailed attributes

### 🛠️ Function Tools (ACP-Inspired)

#### 1. `search_products(query, category, max_price, min_price, brand)`
Search and filter products with intelligent matching
- Supports natural language queries
- Multi-field search (name, description, category, brand)
- Price range filtering
- Returns top 3 matches with ratings

#### 2. `add_to_cart(product_id, quantity)`
Add products to session-based shopping cart
- Handles multiple quantities
- Updates existing items
- Real-time cart total calculation

#### 3. `view_cart()`
Display current cart contents
- Itemized list with quantities and prices
- Running total calculation
- Empty cart handling

#### 4. `remove_from_cart(product_id)`
Remove items from cart
- Product ID-based removal
- Confirmation messages

#### 5. `create_order(customer_name, customer_email, delivery_address)`
Complete purchase and generate order
- Unique order ID generation (ORD-XXXXXXXX)
- ACP-inspired data structure with line_items
- Order status tracking
- Timestamp and metadata
- Cart clearing after order
- Persistent storage to JSON

#### 6. `get_order_history(limit)`
Retrieve past orders
- Sorted by most recent
- Configurable result limit
- Order summary with totals and status

## 🗣️ Voice Interaction Examples

### Product Discovery
- "Show me wireless headphones"
- "I'm looking for books under 500 rupees"
- "Do you have Nike shoes?"
- "What electronics do you have?"

### Cart Management
- "Add the first item to my cart"
- "Put 2 of those in my cart"
- "What's in my cart?"
- "Remove the headphones"

### Checkout
- "I'll buy everything in my cart"
- "Proceed to checkout"
- "Place my order"

### Order History
- "Show me my orders"
- "What did I buy?"

## 📂 File Structure

```
backend/
├── src/
│   └── agent.py              # Main Amazon Voice Agent
├── amazon_products.json      # Product catalog (20 items)
├── amazon_orders.json        # Order history storage
└── .env.local               # API keys
```

## 🔄 Data Models (ACP-Inspired)

### Product Schema
```json
{
  "id": "AMZN-ELEC-001",
  "name": "Sony WH-1000XM5",
  "price": 29990,
  "currency": "INR",
  "category": "Electronics",
  "brand": "Sony",
  "in_stock": true,
  "rating": 4.7
}
```

### Order Schema
```json
{
  "order_id": "ORD-A1B2C3D4",
  "timestamp": "2025-11-29T...",
  "customer_name": "John Doe",
  "status": "CONFIRMED",
  "line_items": [
    {
      "product_id": "AMZN-ELEC-001",
      "quantity": 1,
      "unit_price": 29990,
      "line_total": 29990
    }
  ],
  "subtotal": 29990,
  "currency": "INR"
}
```

## 🚀 Setup & Running

1. **Install dependencies:**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   - Copy `.env.example` to `.env.local`
   - Add your API keys (Murf, Deepgram, Google, etc.)

3. **Start the agent:**
   ```bash
   python src/agent.py dev
   ```

4. **Start frontend:**
   ```bash
   cd frontend
   pnpm install
   pnpm dev
   ```

5. **Open browser:**
   Navigate to `http://localhost:3000`

## 🎨 Brand Customization
The agent is themed for Amazon but can be easily customized:
- Product catalog colors and branding
- Frontend styling (Amazon orange #FF9900)
- Voice personality and tone
- Product categories and inventory

## 🔧 Technical Stack
- **Voice Framework**: LiveKit Agents
- **LLM**: Google Gemini 2.5 Flash
- **TTS**: Murf Falcon (fastest TTS API)
- **STT**: Deepgram Nova 3
- **VAD**: Silero
- **Language**: Python 3.11+

## 📊 Key Features
- ✅ Session-based cart management
- ✅ Persistent order storage
- ✅ Multi-criteria product search
- ✅ Natural language understanding
- ✅ Context-aware conversations
- ✅ ACP-inspired data structures
- ✅ Real-time cart calculations
- ✅ Order confirmation with unique IDs

## 🎯 Challenge Completion
This implementation fulfills all **Primary Goal requirements** for Day 9:
1. ✅ Small product catalog (20 items)
2. ✅ ACP-inspired merchant layer in Python
3. ✅ Voice flow for browsing and ordering
4. ✅ Orders persisted to JSON file
5. ✅ Natural conversation handling
6. ✅ Cart and order history features

## 🔗 Resources Used
- [Agentic Commerce Protocol](https://www.agenticcommerce.dev/)
- [LiveKit Agents Documentation](https://docs.livekit.io/agents/)
- [Murf Falcon TTS](https://murf.ai/)

## 📝 Notes
- Shopping cart is session-based (per room)
- Orders persist across sessions in JSON
- Products can be easily extended/modified
- Ready for advanced goals (HTTP APIs, UI integration)

---

**Built with Murf Falcon - The Fastest TTS API** 🚀
**#MurfAIVoiceAgentsChallenge #10DaysofAIVoiceAgents**
