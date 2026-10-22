import http from "k6/http";
import { check, sleep } from "k6";

const URL = "http://joke-dev-alb-1173751468.us-east-1.elb.amazonaws.com/joke";

export const options = {
  stages: [
    { duration: "1m", target: 20 },
    { duration: "2m", target: 50 },
    { duration: "1m", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1000"],
  },
};

export default function () {
  const res = http.get(URL);
  check(res, { "status is 200": (r) => r.status === 200 });
  sleep(1);
}