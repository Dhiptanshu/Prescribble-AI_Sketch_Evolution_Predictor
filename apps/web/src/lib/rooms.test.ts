import { beforeEach, describe, expect, it } from "vitest";
import { forgetRoomToken, formatClock, liveUrl, loadRoomToken, remaining, saveRoomToken, tokenHeader } from "./rooms";

describe("room helpers", () => {
  it("builds the socket address from the page's own origin and scheme", () => {
    expect(liveUrl({ protocol: "http:", host: "localhost:5173" }, 7)).toBe("ws://localhost:5173/api/v1/rooms/7/live");
    expect(liveUrl({ protocol: "https:", host: "school.example" }, 12)).toBe("wss://school.example/api/v1/rooms/12/live");
  });

  it("counts down from the moment the server's value arrived and never goes negative", () => {
    expect(remaining(30, 1_000, 1_000)).toBe(30);
    expect(remaining(30, 1_000, 11_500)).toBe(19.5);
    expect(remaining(5, 0, 60_000)).toBe(0);
  });

  it("formats the round clock as m:ss, rounding partial seconds up", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(0.2)).toBe("0:01");
    expect(formatClock(59.01)).toBe("1:00");
    expect(formatClock(125)).toBe("2:05");
    expect(formatClock(-3)).toBe("0:00");
  });

  it("sends the room token only when there is one", () => {
    expect(tokenHeader("prs_rm_x")).toEqual({ "X-Room-Token": "prs_rm_x" });
    expect(tokenHeader(null)).toBeUndefined();
  });
});

describe("the student's room token", () => {
  beforeEach(() => localStorage.clear());

  it("is remembered per room and can be forgotten", () => {
    saveRoomToken(3, "prs_rm_abc", "Sam");
    expect(loadRoomToken(3)).toEqual({ token: "prs_rm_abc", nickname: "Sam" });
    expect(loadRoomToken(4)).toBeNull();
    forgetRoomToken(3);
    expect(loadRoomToken(3)).toBeNull();
  });

  it("ignores damaged storage instead of crashing", () => {
    localStorage.setItem("prescribble.room.9", "{not json");
    expect(loadRoomToken(9)).toBeNull();
    localStorage.setItem("prescribble.room.9", JSON.stringify({ token: 5 }));
    expect(loadRoomToken(9)).toBeNull();
  });
});
