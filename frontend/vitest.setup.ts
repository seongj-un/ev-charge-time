import "@testing-library/jest-dom/vitest";

/*
 * jsdom에는 scrollIntoView가 없다. 실제 브라우저에는 전부 있으므로 화면 코드에
 * 방어 코드를 넣는 대신 여기서 메운다 — 없는 환경을 위해 프로덕션에 if를 두면
 * 진짜로 확인해야 할 분기와 섞인다.
 */
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {};
}
