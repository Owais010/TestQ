const express = require('express');
const app = express();
const port = process.env.PORT || 3000;

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// --- API Endpoints ---
app.get('/api/status', (req, res) => {
  res.json({ status: 'healthy', version: '1.0.0' });
});

app.get('/api/products', (req, res) => {
  res.json([
    { id: 1, name: 'Pro Wireless Headphones', price: 99.99 },
    { id: 2, name: 'Mechanical Keyboard', price: 129.99 },
    { id: 3, name: 'Ergonomic Gaming Mouse', price: 59.99 }
  ]);
});

// BUG-002: Login accepts invalid email without format validation
app.post('/api/login', (req, res) => {
  const { email, password } = req.body;
  // Flawed: does not check for valid email format (@ and domain)
  if (!email || !password) {
    return res.status(400).json({ error: 'Missing credentials' });
  }
  // Accepts invalid email like "bademail"
  res.json({ status: 'ok', user: email, token: 'mock-jwt-token-xyz' });
});

// BUG-001: Checkout accepts quantity 0
app.post('/api/checkout', (req, res) => {
  const { quantity, address } = req.body;
  // Flawed: does not validate quantity > 0
  const qty = parseInt(quantity, 10);
  if (isNaN(qty)) {
    return res.status(400).json({ error: 'Quantity must be a number' });
  }
  // BUG: qty === 0 is allowed and treated as an order
  res.json({
    status: 'order_confirmed',
    order_id: 'ORD-' + Math.floor(Math.random() * 90000 + 10000),
    quantity: qty,
    address: address || 'Default Address',
    total: (qty * 99.99).toFixed(2)
  });
});

// --- HTML Pages with semantic markup and test IDs ---

const navBar = `
<nav style="background:#1e293b;padding:12px 24px;display:flex;gap:16px;">
  <a href="/" style="color:#38bdf8;font-weight:bold;text-decoration:none;">DemoStore</a>
  <a href="/products" id="nav-products" style="color:#f1f5f9;text-decoration:none;">Products</a>
  <a href="/cart" id="nav-cart" style="color:#f1f5f9;text-decoration:none;">Cart</a>
  <a href="/checkout" id="nav-checkout" style="color:#f1f5f9;text-decoration:none;">Checkout</a>
  <a href="/login" id="nav-login" style="color:#f1f5f9;text-decoration:none;">Login</a>
</nav>
`;

app.get('/', (req, res) => {
  res.send(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>TestQ Demo Store — Home</title>
  <style>body{font-family:sans-serif;margin:0;background:#0f172a;color:#f8fafc;}</style>
</head>
<body>
  ${navBar}
  <div style="padding:40px;max-width:800px;margin:auto;">
    <h1 data-testid="store-title">Welcome to TestQ Demo Store</h1>
    <p>A modern e-commerce storefront with intentional bugs for automated AI QA testing.</p>
    <div style="display:flex;gap:12px;margin-top:20px;">
      <a href="/products"><button data-testid="shop-now-btn" style="padding:10px 20px;background:#38bdf8;border:none;border-radius:6px;cursor:pointer;font-weight:bold;">Shop Now</button></a>
      <a href="/login"><button data-testid="home-login-btn" style="padding:10px 20px;background:#334155;color:white;border:none;border-radius:6px;cursor:pointer;">Login</button></a>
    </div>
  </div>
</body>
</html>`);
});

app.get('/products', (req, res) => {
  res.send(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>TestQ Demo Store — Products</title>
  <style>body{font-family:sans-serif;margin:0;background:#0f172a;color:#f8fafc;}.card{background:#1e293b;padding:20px;border-radius:8px;margin-bottom:16px;}</style>
</head>
<body>
  ${navBar}
  <div style="padding:40px;max-width:800px;margin:auto;">
    <h1>Available Products</h1>
    <div class="card">
      <h3>Pro Wireless Headphones</h3>
      <p>$99.99</p>
      <a href="/cart"><button data-testid="add-headphones-btn" style="padding:8px 16px;background:#38bdf8;border:none;border-radius:4px;cursor:pointer;">Add to Cart</button></a>
    </div>
    <div class="card">
      <h3>Mechanical Keyboard</h3>
      <p>$129.99</p>
      <a href="/cart"><button data-testid="add-keyboard-btn" style="padding:8px 16px;background:#38bdf8;border:none;border-radius:4px;cursor:pointer;">Add to Cart</button></a>
    </div>
  </div>
</body>
</html>`);
});

app.get('/login', (req, res) => {
  res.send(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>TestQ Demo Store — Login</title>
  <style>body{font-family:sans-serif;margin:0;background:#0f172a;color:#f8fafc;}input{display:block;width:100%;padding:10px;margin:8px 0 16px;border-radius:4px;border:1px solid #475569;background:#1e293b;color:#f8fafc;}</style>
</head>
<body>
  ${navBar}
  <div style="padding:40px;max-width:400px;margin:auto;">
    <h1>Account Login</h1>
    <form id="login-form" action="/api/login" method="post">
      <label>Email Address</label>
      <input type="text" id="email-input" data-testid="email-input" name="email" value="user@example.com">
      
      <label>Password</label>
      <input type="password" id="password-input" data-testid="password-input" name="password" value="password123">
      
      <button type="submit" id="login-submit-btn" data-testid="login-submit-btn" style="width:100%;padding:12px;background:#38bdf8;border:none;border-radius:4px;font-weight:bold;cursor:pointer;">Sign In</button>
    </form>
  </div>
</body>
</html>`);
});

app.get('/cart', (req, res) => {
  res.send(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>TestQ Demo Store — Cart</title>
  <style>body{font-family:sans-serif;margin:0;background:#0f172a;color:#f8fafc;}</style>
</head>
<body>
  ${navBar}
  <div style="padding:40px;max-width:600px;margin:auto;">
    <h1>Your Shopping Cart</h1>
    <div style="background:#1e293b;padding:20px;border-radius:8px;">
      <p><strong>Item:</strong> Pro Wireless Headphones (1x) - $99.99</p>
      <p><strong>Subtotal:</strong> $99.99</p>
      
      <!-- BUG-003: Broken link to /checkout-broken instead of /checkout -->
      <a id="cart-checkout-link" data-testid="cart-checkout-link" href="/checkout-broken">
        <button id="checkout-nav-btn" data-testid="checkout-nav-btn" style="padding:10px 20px;background:#22c55e;color:white;border:none;border-radius:4px;cursor:pointer;font-weight:bold;">
          Proceed to Checkout
        </button>
      </a>
    </div>
  </div>
</body>
</html>`);
});

app.get('/checkout', (req, res) => {
  res.send(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>TestQ Demo Store — Checkout</title>
  <style>body{font-family:sans-serif;margin:0;background:#0f172a;color:#f8fafc;}input{display:block;width:100%;padding:10px;margin:8px 0 16px;border-radius:4px;border:1px solid #475569;background:#1e293b;color:#f8fafc;}</style>
</head>
<body>
  ${navBar}
  <div style="padding:40px;max-width:500px;margin:auto;">
    <h1>Order Checkout</h1>
    <form id="checkout-form" action="/api/checkout" method="post">
      <label>Item Quantity</label>
      <!-- BUG-001: Accepts quantity 0 without error -->
      <input type="number" id="quantity-input" data-testid="quantity-input" name="quantity" value="1">
      
      <label>Shipping Address</label>
      <input type="text" id="address-input" data-testid="address-input" name="address" value="123 AI Boulevard">
      
      <button type="submit" id="place-order-btn" data-testid="place-order-btn" style="width:100%;padding:12px;background:#22c55e;color:white;border:none;border-radius:4px;font-weight:bold;cursor:pointer;">
        Place Order
      </button>
    </form>
  </div>
</body>
</html>`);
});

app.listen(port, '0.0.0.0', () => {
  console.log('TestQ Demo Store running on port ' + port);
});
