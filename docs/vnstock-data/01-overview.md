# Vnstock Data - Hướng Dẫn Toàn Diện cho AI Agents

## Giới Thiệu

`vnstock_data` là thư viện Python cung cấp khả năng truy xuất toàn diện dữ liệu thị trường chứng khoán Việt Nam từ nhiều nguồn dữ liệu đáng tin cậy. Thư viện sử dụng **Adapter Pattern** để cho phép chuyển đổi dễ dàng giữa các nguồn dữ liệu mà không cần thay đổi code logic chính.

### Cấu Trúc Thư Viện

Thư viện được tổ chức theo cấu trúc module rõ ràng để dễ dàng bảo trì và mở rộng:

```
vnstock_data/
├── __init__.py          # Khởi tạo package, export các class chính
├── base.py              # Base classes và utilities chung
├── config.py            # Cấu hình toàn cục
├── api/                 # API interfaces thống nhất
│   ├── __init__.py
│   ├── commodity.py     # Dữ liệu hàng hóa
│   ├── company.py       # Thông tin công ty
│   ├── financial.py     # Báo cáo tài chính
│   ├── insight.py       # Phân tích insights
│   ├── listing.py       # Danh sách niêm yết
│   ├── macro.py         # Kinh tế vĩ mô
│   ├── market.py        # Dữ liệu thị trường
│   ├── quote.py         # Dữ liệu giá
│   └── trading.py       # Dữ liệu giao dịch
├── core/               # Core utilities
│   ├── __init__.py
│   ├── const.py        # Constants
│   └── utils/          # Utility functions
├── explorer/           # Data explorers cho từng nguồn
│   ├── __init__.py
│   ├── cafef/          # CafeF data source
│   ├── fmarket/        # Fmarket data source
│   ├── mas/            # MAS data source
│   ├── mbk/            # MBK data source
│   ├── spl/            # SPL data source
│   ├── vci/            # VCI data source
│   └── vnd/            # VND data source
└── ui/                 # User interface components
    └── __init__.py
```

**Giải thích cấu trúc:**
- **`api/`**: Chứa các interface thống nhất cho từng loại dữ liệu (giá, công ty, tài chính, v.v.)
- **`explorer/`**: Implementations cụ thể cho từng nguồn dữ liệu (VCI, VND, CafeF, v.v.)
- **`core/`**: Utilities và constants dùng chung
- **`ui/`**: Components giao diện người dùng (nếu có)

### Đặc Điểm Chính

- **Linh hoạt đa nguồn**: Hỗ trợ các nguồn VCI, VND, MAS, CafeF, v.v.
- **API thống nhất**: Một chuẩn giao tiếp duy nhất cho tất cả loại dữ liệu
- **Dữ liệu phong phú**: Cổ phiếu, chỉ số, trái phiếu, chứng quyền, hàng hóa, kinh tế vĩ mô
- **Hiệu suất cao**: Caching, retry logic, rate limit handling
- **Xử lý lỗi mạnh mẽ**: Tự động retry khi kết nối mất
- **Minh bạch**: Dữ liệu công khai, có thể kiểm tra và ghi nguồn.

### Các Loại Dữ Liệu Chính

| Loại Dữ Liệu | Lớp | Mô Tả |
|---|---|---|
| **Niêm Yết** | `Listing` | Danh sách cổ phiếu, chỉ số, chứng quyền |
| **Giá Lịch Sử** | `Quote` | OHLCV, intraday, price depth |
| **Công Ty** | `Company` | Thông tin, cổ đông, ban lãnh đạo |
| **Tài Chính** | `Finance` | BCTC, chỉ số tài chính, kế hoạch |
| **Giao Dịch** | `Trading` | Bảng giá, thống kê, nước ngoài, nội bộ |
| **Thị Trường** | `Market` | Định giá P/E, P/B |
| **Khám phá** | `TopStock` | Top gainer, loser, volume, deal, vv |
| **Kinh Tế Vĩ Mô** | `Macro` | GDP, CPI, FDI, tỷ giá, vv |
| **Hàng Hóa** | `CommodityPrice` | Vàng, dầu, gas, sắt, giá thịt heo, vv |
| **Quỹ** | `Fund` | Thông tin quỹ ETF, chứng chỉ quỹ |

### Cài Đặt Thư Viện

Các gói thư viện vnstock_data được cài đặt **chung** thông qua chương trình cài đặt của Vnstock. Để cài đặt và kích hoạt vnstock_data, vui lòng tham khảo hướng dẫn chi tiết tại **[Hướng Dẫn Cài Đặt Vnstock](https://vnstocks.com/onboard-member)**.

### Cách Sử Dụng Cơ Bản

#### 1. Cách Thứ Nhất: Adapter Chung (Khuyến Nghị cho Linh Hoạt)

```python
from vnstock_data import Quote, Finance, Trading

# Chỉ định nguồn dữ liệu
quote = Quote(source="vci", symbol="VCB")
df_price = quote.history(start="2024-01-01", end="2024-12-31", interval="1D")

# Dễ dàng đổi nguồn nếu cần
quote_vnd = Quote(source="vnd", symbol="VCB")
df_price_vnd = quote_vnd.history(start="2024-01-01", end="2024-12-31", interval="1D")
```

**Ưu điểm:**
- Linh hoạt thay đổi nguồn
- Code dễ bảo trì
- Thử test nhiều nguồn dễ dàng

**Nhược điểm:**
- Không phải nguồn nào cũng hỗ trợ tất cả methods
- Cần kiểm tra ma trận phương thức được hỗ trợ của từng nguồn

#### 2. Cách Thứ Hai: Import Trực Tiếp (Khuyến Nghị cho Ổn Định)

```python
from vnstock_data.explorer.vci import Quote, Finance, Trading

# Sử dụng trực tiếp từ nguồn cụ thể
quote = Quote(symbol="VCB")
df_price = quote.history(start="2024-01-01", end="2024-12-31", interval="1D")
```

**Ưu điểm:**
- Ổn định, không có lỗi "method not supported"
- Hiệu suất có thể tốt hơn
- Có thể sử dụng features riêng của từng nguồn

**Nhược điểm:**
- Cần thay đổi import khi chuyển nguồn
- Cần nhớ địa chỉ import của của nguồn trong thư viện

### Các Nguồn Dữ Liệu Chính

| Tên | Code | Mô Tả | Ưu Điểm |
|---|---|---|---|
| **VCI** | `vci` | Dữ liệu từ Vietcap | Dữ liệu phong phú, support đầy đủ |
| **VND** | `vnd` | VNDirect | Dữ liệu đầy đủ, nhanh chóng |
| **MAS** | `mas` | Mirae Asset | BCTC định dạng Excel-style |
| **CafeF** | `cafef` | CafeF Vietnam | Dữ liệu phong phú |
| **MBK** | `mbk` | Maybank Kimeng - Kinh tế Vĩ Mô | Dữ liệu kinh tế vĩ mô |
| **SPL** | `spl` | Dữ Lệu Hàng Hóa | Giá hàng hóa |

### Lý Do Sử Dụng Vnstock_data

1. **Toàn Diện**: Cung cấp tất cả loại dữ liệu từ giá, BCTC đến kinh tế vĩ mô
2. **Đáng Tin**: Kết nối từ các website công ty chứng khoán & nguồn dữ lệu uy tín (VCI, VND, VCI,...)
3. **Linh Hoạt**: Dễ dàng chuyển đổi giữa các nguồn
4. **Bảo Trì**: Được update thường xuyên, support tốt
5. **Cộng Đồng**: Có cộng đồng người dùng lớn, tài liệu đầy đủ

### Miễn Trừ Trách Nhiệm

- Dữ liệu được cung cấp **chỉ nhằm mục đích nghiên cứu, giáo dục, sử dụng cá nhân**
- Không sử dụng dữ liệu này làm cơ sở duy nhất cho quyết định giao dịch thực tế
- Dữ liệu có thể không đầy đủ, không liên tục hoặc có sai lệch so với nguồn gốc
- Vnstock và tác giả **không chịu trách nhiệm** về bất kỳ tổn thất nào phát sinh từ việc sử dụng dữ liệu

### Cấu Trúc Tài Liệu Này

Tài liệu được chia thành các phần chính:

1. **[01-overview.md](01-overview.md)** (Tệp này) - Tổng quan, cách sử dụng cơ bản
2. **[02-listing.md](02-listing.md)** - Danh sách niêm yết, phân ngành, chỉ số
3. **[03-quote.md](03-quote.md)** - Lịch sử giá, OHLCV, intraday, price depth
4. **[04-company.md](04-company.md)** - Thông tin công ty, cổ đông, ban lãnh đạo
5. **[05-finance.md](05-finance.md)** - Báo cáo tài chính, chỉ số, kế hoạch
6. **[06-trading.md](06-trading.md)** - Giao dịch, bảng giá, thống kê
7. **[07-market.md](07-market.md)** - Định giá thị trường (P/E, P/B)
8. **[08-insights.md](08-insights.md)** - Top stock (gainer, loser, volume, deal)
9. **[09-macro.md](09-macro.md)** - Kinh tế vĩ mô (GDP, CPI, FDI, tỷ giá)
10. **[10-commodity.md](10-commodity.md)** - Giá hàng hóa (vàng, dầu, khí, nông sản)
11. **[11-fund.md](11-fund.md)** - Dữ liệu quỹ ETF
12. **[12-data-sources.md](12-data-sources.md)** - Ma trận support các nguồn dữ liệu
13. **[13-best-practices.md](13-best-practices.md)** - Best practices và tips sử dụng

> **Lưu ý**: Để tìm hiểu chi tiết hơn về các lỗi phổ biến, tips tối ưu, templates sử dụng và so sánh các nguồn dữ liệu, vui lòng xem **[README.md](README.md)**.
