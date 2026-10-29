/* AppNho News — gửi page_view lên GA4 (G-K9C4KKZPEE) với đúng tiêu đề trang.
   - Thẻ gtag trong <head> đã tắt page_view tự động (send_page_view:false).
   - Trang bài viết (article.html) và trang chuyên mục (?category=...) đặt document.title bằng JavaScript
     sau khi tải dữ liệu, nên chờ tiêu đề đổi rồi mới gửi để báo cáo GA4 hiển thị tên từng bài.
   - Có đồng hồ dự phòng 6 giây: dù JavaScript của trang lỗi, lượt xem vẫn được ghi.
   Mọi bài tự động đăng sau này đều mở qua article.html?id=<id> nên được ghi tự động. */
(function () {
  if (typeof window.gtag !== 'function') return;
  var sent = false;
  function send() {
    if (sent) return;
    sent = true;
    window.gtag('event', 'page_view', {
      page_title: document.title,
      page_location: location.href,
      page_path: location.pathname + location.search
    });
  }
  var waitForTitle = /article(\.html)?$/.test(location.pathname) || /[?&]category=/.test(location.search);
  if (!waitForTitle) { send(); return; }
  var initial = document.title, titleEl = document.querySelector('title');
  if (window.MutationObserver && titleEl) {
    new MutationObserver(function (_, obs) {
      if (document.title !== initial) { obs.disconnect(); send(); }
    }).observe(titleEl, { childList: true, characterData: true, subtree: true });
  }
  setTimeout(send, 6000);
  window.addEventListener('pagehide', send);
})();
