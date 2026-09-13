const net = require("net");
const readline = require("readline");

function send(host, port, payload) {
  return new Promise((resolve, reject) => {
    const s = new net.Socket();
    s.setTimeout(5000);
    const body = Buffer.from(JSON.stringify(payload), "utf-8");
    const hdr = Buffer.alloc(5);
    hdr.writeUInt8(0, 0);
    hdr.writeUInt32BE(body.length, 1);

    s.connect(port, host, () => {
      s.write(Buffer.concat([hdr, body]));
    });

    s.on("data", (data) => {
      s.destroy();
      try {
        const len = data.readUInt32BE(1);
        const jsonStr = data.subarray(5, 5 + len).toString("utf-8");
        resolve(JSON.parse(jsonStr));
      } catch (err) {
        resolve({ raw: data.toString() });
      }
    });

    s.on("timeout", () => {
      s.destroy();
      reject(new Error("Connection timed out"));
    });

    s.on("error", (err) => {
      reject(err);
    });
  });
}

async function main() {
  console.log("=== LG Music Flow Speaker Setup & Wi-Fi Provisioning ===");
  console.log("Connect to the speaker's temporary Wi-Fi network (or connect via Ethernet).");
  console.log("");

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  const question = (q, def) =>
    new Promise((resolve) => {
      rl.question(`${q}${def ? ` [${def}]` : ""}: `, (ans) => {
        resolve(ans.trim() || def);
      });
    });

  try {
    const host = await question("Speaker IP address", "192.168.5.100");
    const port = 9741;

    console.log(`\nConnecting to speaker at ${host}:${port}...`);
    const infoRes = await send(host, port, {
      msg: "PRODUCT_INFO",
      data: { day: 1, hour: 0, min: 0, option: 0, id: "setup00000000000" },
    });

    if (infoRes && infoRes.data) {
      console.log(`Found: ${infoRes.data.modelname || "LG Music Flow"} (MAC: ${infoRes.data.info?.wirelessmac || "Unknown"})`);
    } else {
      console.log("Connected to speaker.");
    }

    const ssid = await question("\nHome Wi-Fi Network Name (SSID - 2.4GHz)", "");
    if (!ssid) {
      console.error("SSID cannot be empty.");
      process.exit(1);
    }

    const pwd = await question("Wi-Fi Password", "");
    const name = await question("Speaker Name (optional, press Enter to skip)", "");

    if (name) {
      console.log(`Setting speaker name to "${name}"...`);
      await send(host, port, {
        msg: "SPK_INFO_MODIFY",
        data: { name: name },
      });
      console.log("Name set successfully.");
    }

    console.log(`Sending Wi-Fi credentials for "${ssid}"...`);
    const wifiRes = await send(host, port, {
      msg: "SHARE_HOME_INFO",
      data: { ssid: ssid, pwd: pwd, auth: 0 },
    });

    console.log("Response:", wifiRes);
    console.log("\nSuccess! The speaker will now reboot its Wi-Fi module and join your network.");
    console.log("Once connected, it will be automatically discovered in Home Assistant!");
  } catch (err) {
    console.error("\nError during setup:", err.message);
    console.log("Ensure your computer is connected to the speaker's Wi-Fi (default IP 192.168.5.100) or Ethernet cable.");
  } finally {
    rl.close();
  }
}

main();
