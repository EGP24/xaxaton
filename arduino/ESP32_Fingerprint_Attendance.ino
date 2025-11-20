

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <HardwareSerial.h>



const char* WIFI_SSID = "MERCUSYS_FBC6";
const char* WIFI_PASSWORD = "79177788";


const char* SERVER_URL = "http://192.168.1.106:8888";  
const char* API_TEMPLATES = "/api/fingerprint/students/templates";
const char* API_ENROLL = "/api/fingerprint/enroll";
const char* API_IDENTIFY = "/api/fingerprint/identify";


String CLASSROOM = "101";


#define BUTTON_ENROLL_PIN 15   
#define LED_STATUS_PIN 2       
#define LED_SUCCESS_PIN 4      
#define LED_ERROR_PIN 5        


#define AS608_RX_PIN 16  
#define AS608_TX_PIN 17  
#define AS608_BAUDRATE 57600
#define AS608_UART_NUM 2


#define AS608_ADDRESS 0xFFFFFFFF
#define AS608_PASSWORD 0x00000000


#define AS608_GETIMAGE 0x01
#define AS608_IMAGE2TZ 0x02
#define AS608_SEARCH 0x04
#define AS608_REGMODEL 0x05
#define AS608_STORE 0x06
#define AS608_LOAD 0x07
#define AS608_UPCHAR 0x08
#define AS608_DOWNCHAR 0x09
#define AS608_EMPTY 0x0D
#define AS608_VERIFYPASSWORD 0x13


#define AS608_COMMANDPACKET 0x01
#define AS608_DATAPACKET 0x02
#define AS608_ACKPACKET 0x07
#define AS608_ENDDATAPACKET 0x08


#define AS608_OK 0x00
#define AS608_NOFINGER 0x02
#define AS608_IMAGEFAIL 0x03
#define AS608_FEATUREFAIL 0x07
#define AS608_NOMATCH 0x08
#define AS608_NOTFOUND 0x09
#define AS608_ENROLLMISMATCH 0x0A


#define AS608_PACKET_MAX_SIZE 512
#define AS608_TEMPLATE_MAX_SIZE 768


HardwareSerial AS608Serial(AS608_UART_NUM);

bool enrollMode = false;
int enrollStudentId = -1;

uint8_t packetBuffer[AS608_PACKET_MAX_SIZE];
uint8_t templateBuffer[AS608_TEMPLATE_MAX_SIZE];
uint16_t templateSize = 0;


struct AS608Packet {
  uint16_t start;
  uint32_t address;
  uint8_t type;
  uint16_t length;
  uint8_t data[AS608_PACKET_MAX_SIZE];
};



void writePacket(uint32_t address, uint8_t packetType, uint16_t length, uint8_t *data);
int readPacket(AS608Packet *packet, uint16_t timeout = 1000);
uint16_t calculateChecksum(uint8_t packetType, uint16_t length, uint8_t *data);
bool verifyPassword();
uint8_t getImage();
uint8_t image2Tz(uint8_t slot);
uint8_t createModel();
uint8_t storeModel(uint8_t slot, uint16_t id);
uint8_t searchFinger(uint8_t slot, uint16_t *id, uint16_t *confidence);
uint8_t uploadTemplate(uint8_t slot, uint8_t *templateData, uint16_t *size);
uint8_t downloadTemplate(uint8_t slot, uint8_t *templateData, uint16_t size);
uint8_t emptyDatabase();


void connectWiFi();
bool sendEnrollToServer(int studentId, String fingerTemplate);
bool sendIdentifyToServer(String scannedTemplate);


void blinkSuccess(int times);
void blinkError(int times);
void hexStringToBytes(String hex, uint8_t* output, int length);
String bytesToHexString(uint8_t* data, uint16_t length);


void setup() {
  Serial.begin(115200);
  Serial.println("\n\n=== Система учета посещаемости ESP32 ===");
  Serial.println("Низкоуровневая реализация AS608\n");


  pinMode(BUTTON_ENROLL_PIN, INPUT_PULLUP);
  pinMode(LED_STATUS_PIN, OUTPUT);
  pinMode(LED_SUCCESS_PIN, OUTPUT);
  pinMode(LED_ERROR_PIN, OUTPUT);

  digitalWrite(LED_STATUS_PIN, LOW);
  digitalWrite(LED_SUCCESS_PIN, LOW);
  digitalWrite(LED_ERROR_PIN, LOW);


  AS608Serial.begin(AS608_BAUDRATE, SERIAL_8N1, AS608_RX_PIN, AS608_TX_PIN);
  delay(500);

  Serial.println("Проверка подключения AS608...");
  if (verifyPassword()) {
    Serial.println("✓ Сканер отпечатков AS608 подключен!");
  } else {
    Serial.println("✗ Сканер AS608 не найден. Проверьте подключение!");
    blinkError(5);
    while (1) { delay(1000); }
  }


  connectWiFi();


  Serial.println("Очистка памяти сканера...");
  emptyDatabase();

  Serial.println("\nСистема готова!");
  Serial.println("Аудитория: " + CLASSROOM);
  Serial.println("Удерживайте кнопку ENROLL для регистрации отпечатка");
  Serial.println("Просто приложите палец для отметки посещаемости");
  blinkSuccess(2);
}


void loop() {

  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }


  if (digitalRead(BUTTON_ENROLL_PIN) == LOW) {
    delay(50); 
    if (digitalRead(BUTTON_ENROLL_PIN) == LOW) {
      enterEnrollMode();
      while (digitalRead(BUTTON_ENROLL_PIN) == LOW) delay(10);
      return;
    }
  }


  if (!enrollMode) {
    checkAttendance();
  }

  delay(100);
}


void connectWiFi() {
  Serial.print("Connecting to WiFi");
  digitalWrite(LED_STATUS_PIN, HIGH);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✓ WiFi connected!");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
    digitalWrite(LED_STATUS_PIN, LOW);
  } else {
    Serial.println("\n✗ WiFi connection failed!");
    blinkError(3);
  }
}


void enterEnrollMode() {
  enrollMode = true;
  Serial.println("\n=== РЕЖИМ РЕГИСТРАЦИИ ===");
  Serial.println("Введите ID студента в Serial Monitor:");


  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_SUCCESS_PIN, HIGH);
    delay(200);
    digitalWrite(LED_SUCCESS_PIN, LOW);
    delay(200);
  }


  enrollStudentId = -1;
  unsigned long startTime = millis();

  while (enrollStudentId == -1 && millis() - startTime < 30000) {
    if (Serial.available() > 0) {
      String input = Serial.readStringUntil('\n');
      input.trim();
      enrollStudentId = input.toInt();

      if (enrollStudentId > 0) {
        Serial.println("ID студента: " + String(enrollStudentId));
        Serial.println("Приложите палец к сканеру...");


        if (enrollFingerprint(enrollStudentId)) {
          Serial.println("✓ Отпечаток успешно зарегистрирован!");
          blinkSuccess(3);
        } else {
          Serial.println("✗ Ошибка регистрации!");
          blinkError(3);
        }
      } else {
        Serial.println("Неверный ID!");
      }
    }
    delay(100);
  }

  if (enrollStudentId == -1) {
    Serial.println("Время ожидания истекло - выход из режима регистрации");
  }

  enrollMode = false;
  enrollStudentId = -1;
}

bool enrollFingerprint(int studentId) {
  Serial.println("Сканирование пальца (1/2)...");


  uint8_t result = AS608_NOFINGER;
  while (result != AS608_OK) {
    result = getImage();
    if (result != AS608_OK && result != AS608_NOFINGER) {
      Serial.println("Ошибка сканирования пальца");
      return false;
    }
    delay(50);
  }

  result = image2Tz(1);
  if (result != AS608_OK) {
    Serial.println("Ошибка преобразования изображения (1)");
    return false;
  }

  Serial.println("✓ Первое сканирование успешно!");
  Serial.println("Уберите палец...");
  delay(2000);


  while (getImage() != AS608_NOFINGER) {
    delay(100);
  }

  Serial.println("Приложите тот же палец снова (2/2)...");


  result = AS608_NOFINGER;
  while (result != AS608_OK) {
    result = getImage();
    if (result != AS608_OK && result != AS608_NOFINGER) {
      Serial.println("Ошибка сканирования пальца");
      return false;
    }
    delay(50);
  }

  result = image2Tz(2);
  if (result != AS608_OK) {
    Serial.println("Ошибка преобразования изображения (2)");
    return false;
  }

  Serial.println("✓ Второе сканирование успешно!");


  result = createModel();
  if (result != AS608_OK) {
    Serial.println("Отпечатки не совпадают");
    return false;
  }

  Serial.println("✓ Модель создана!");


  templateSize = 0;
  result = uploadTemplate(1, templateBuffer, &templateSize);
  if (result != AS608_OK) {
    Serial.println("Ошибка выгрузки шаблона");
    return false;
  }

  Serial.printf("✓ Шаблон экспортирован, размер: %d байт\n", templateSize);


  String hexTemplate = bytesToHexString(templateBuffer, templateSize);


  return sendEnrollToServer(studentId, hexTemplate);
}

bool sendEnrollToServer(int studentId, String fingerTemplate) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi не подключен!");
    return false;
  }

  HTTPClient http;
  String url = String(SERVER_URL) + API_ENROLL;
  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<2048> doc;
  doc["student_id"] = studentId;
  doc["fingerprint_template"] = fingerTemplate;

  String requestBody;
  serializeJson(doc, requestBody);

  Serial.println("Отправка на сервер...");
  int httpCode = http.POST(requestBody);

  if (httpCode == 200) {
    String response = http.getString();
    Serial.println("Ответ сервера: " + response);
    http.end();
    return true;
  } else {
    Serial.println("Ошибка HTTP: " + String(httpCode));
    http.end();
    return false;
  }
}


void checkAttendance() {
  static unsigned long lastCheck = 0;


  if (millis() - lastCheck < 2000) {
    return;
  }
  lastCheck = millis();

  Serial.println("\n--- Проверка наличия пальца ---");
  digitalWrite(LED_STATUS_PIN, HIGH);


  uint8_t result = getImage();
  if (result != AS608_OK) {
    digitalWrite(LED_STATUS_PIN, LOW);
    return;
  }

  Serial.println("Палец обнаружен! Загрузка шаблонов...");


  if (!loadTemplatesFromServer()) {
    Serial.println("Не удалось загрузить шаблоны!");
    blinkError(2);
    digitalWrite(LED_STATUS_PIN, LOW);
    return;
  }


  Serial.println("Сканирование...");
  result = image2Tz(1);
  if (result != AS608_OK) {
    Serial.println("Ошибка преобразования изображения");
    emptyDatabase();
    blinkError(1);
    digitalWrite(LED_STATUS_PIN, LOW);
    return;
  }



  uint16_t matchedId = 0;
  uint16_t confidence = 0;
  result = searchFinger(1, &matchedId, &confidence);

  if (result == AS608_OK) {
    Serial.printf("✓ Совпадение найдено!\n");
    Serial.printf("  ID студента: %d\n", matchedId);
    Serial.printf("  Совпадение: %d%%\n", confidence);


    if (sendIdentifyToServer(matchedId)) {
      blinkSuccess(2);
    } else {
      blinkError(2);
    }
  } else if (result == AS608_NOTFOUND) {
    Serial.println("Совпадение не найдено");
    blinkError(1);
  } else {
    Serial.println("Ошибка поиска");
    blinkError(2);
  }


  emptyDatabase();
  digitalWrite(LED_STATUS_PIN, LOW);
}

bool loadTemplatesFromServer() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi не подключен!");
    return false;
  }

  HTTPClient http;
  String url = String(SERVER_URL) + API_TEMPLATES + "?classroom=" + CLASSROOM;
  http.begin(url);

  Serial.println("GET: " + url);
  int httpCode = http.GET();

  if (httpCode != 200) {
    Serial.println("Ошибка HTTP: " + String(httpCode));
    http.end();
    return false;
  }

  String response = http.getString();
  http.end();


  DynamicJsonDocument doc(8192);
  DeserializationError error = deserializeJson(doc, response);

  if (error) {
    Serial.println("Ошибка парсинга JSON!");
    return false;
  }

  int count = doc.size();
  Serial.printf("Загрузка %d шаблонов...\n", count);


  int loaded = 0;
  for (int i = 0; i < count && i < 100; i++) {  
    int studentId = doc[i]["id"];
    String hexTemplate = doc[i]["fingerprint_template"].as<String>();


    uint16_t tempSize = hexTemplate.length() / 2;
    if (tempSize > AS608_TEMPLATE_MAX_SIZE) {
      Serial.printf("Шаблон слишком большой для студента %d\n", studentId);
      continue;
    }

    uint8_t tempBuffer[AS608_TEMPLATE_MAX_SIZE];
    hexStringToBytes(hexTemplate, tempBuffer, tempSize);


    uint8_t result = downloadTemplate(1, tempBuffer, tempSize);
    if (result == AS608_OK) {
      result = storeModel(1, studentId);
      if (result == AS608_OK) {
        Serial.printf("Загружено: Студент %d -> Слот %d\n", studentId, studentId);
        loaded++;
      } else {
        Serial.printf("Не удалось сохранить для студента %d\n", studentId);
      }
    } else {
      Serial.printf("Не удалось загрузить для студента %d\n", studentId);
    }
  }

  Serial.printf("✓ Шаблонов загружено: %d/%d\n", loaded, count);
  return loaded > 0;
}

bool sendIdentifyToServer(int studentId) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi не подключен!");
    return false;
  }

  HTTPClient http;
  String url = String(SERVER_URL) + API_IDENTIFY;
  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<256> doc;
  doc["classroom"] = CLASSROOM;
  doc["student_id"] = studentId;

  String requestBody;
  serializeJson(doc, requestBody);

  Serial.printf("Отметка посещаемости для студента ID %d...\n", studentId);
  int httpCode = http.POST(requestBody);

  if (httpCode == 200) {
    String response = http.getString();
    Serial.println("✓ Ответ сервера:");


    StaticJsonDocument<512> respDoc;
    deserializeJson(respDoc, response);

    bool success = respDoc["success"];
    String studentName = respDoc["student_name"].as<String>();
    String message = respDoc["message"].as<String>();

    if (success) {
      Serial.println("✓ " + studentName + " - посещаемость отмечена!");
    }
    Serial.println(message);

    http.end();
    return success;
  } else {
    Serial.println("✗ Ошибка HTTP: " + String(httpCode));
    http.end();
    return false;
  }
}



bool verifyPassword() {
  AS608Packet packet;
  packet.data[0] = AS608_VERIFYPASSWORD;
  packet.data[1] = (AS608_PASSWORD >> 24) & 0xFF;
  packet.data[2] = (AS608_PASSWORD >> 16) & 0xFF;
  packet.data[3] = (AS608_PASSWORD >> 8) & 0xFF;
  packet.data[4] = AS608_PASSWORD & 0xFF;

  writePacket(AS608_ADDRESS, AS608_COMMANDPACKET, 5, packet.data);

  if (readPacket(&packet) > 0) {
    return packet.data[0] == AS608_OK;
  }
  return false;
}

uint8_t getImage() {
  AS608Packet packet;
  packet.data[0] = AS608_GETIMAGE;

  writePacket(AS608_ADDRESS, AS608_COMMANDPACKET, 1, packet.data);

  if (readPacket(&packet, 5000) > 0) {
    return packet.data[0];
  }
  return AS608_NOFINGER;
}

uint8_t image2Tz(uint8_t slot) {
  AS608Packet packet;
  packet.data[0] = AS608_IMAGE2TZ;
  packet.data[1] = slot;

  writePacket(AS608_ADDRESS, AS608_COMMANDPACKET, 2, packet.data);

  if (readPacket(&packet, 5000) > 0) {
    return packet.data[0];
  }
  return AS608_FEATUREFAIL;
}

uint8_t createModel() {
  AS608Packet packet;
  packet.data[0] = AS608_REGMODEL;

  writePacket(AS608_ADDRESS, AS608_COMMANDPACKET, 1, packet.data);

  if (readPacket(&packet) > 0) {
    return packet.data[0];
  }
  return AS608_ENROLLMISMATCH;
}

uint8_t storeModel(uint8_t slot, uint16_t id) {
  AS608Packet packet;
  packet.data[0] = AS608_STORE;
  packet.data[1] = slot;
  packet.data[2] = (id >> 8) & 0xFF;
  packet.data[3] = id & 0xFF;

  writePacket(AS608_ADDRESS, AS608_COMMANDPACKET, 4, packet.data);

  if (readPacket(&packet) > 0) {
    return packet.data[0];
  }
  return 0xFF;
}

uint8_t searchFinger(uint8_t slot, uint16_t *id, uint16_t *confidence) {
  AS608Packet packet;
  packet.data[0] = AS608_SEARCH;
  packet.data[1] = slot;
  packet.data[2] = 0x00;  
  packet.data[3] = 0x00;  
  packet.data[4] = 0x03;  
  packet.data[5] = 0xE8;  

  writePacket(AS608_ADDRESS, AS608_COMMANDPACKET, 6, packet.data);

  if (readPacket(&packet) > 0) {
    if (packet.data[0] == AS608_OK) {
      *id = (packet.data[1] << 8) | packet.data[2];
      *confidence = (packet.data[3] << 8) | packet.data[4];
    }
    return packet.data[0];
  }
  return AS608_NOTFOUND;
}

uint8_t uploadTemplate(uint8_t slot, uint8_t *templateData, uint16_t *size) {
  AS608Packet packet;
  packet.data[0] = AS608_UPCHAR;
  packet.data[1] = slot;

  writePacket(AS608_ADDRESS, AS608_COMMANDPACKET, 2, packet.data);


  if (readPacket(&packet) <= 0 || packet.data[0] != AS608_OK) {
    return packet.data[0];
  }


  *size = 0;
  bool endPacket = false;

  while (!endPacket && *size < AS608_TEMPLATE_MAX_SIZE) {
    int len = readPacket(&packet, 5000);
    if (len <= 0) break;

    endPacket = (packet.type == AS608_ENDDATAPACKET);

    uint16_t dataLen = len;
    if (*size + dataLen > AS608_TEMPLATE_MAX_SIZE) {
      dataLen = AS608_TEMPLATE_MAX_SIZE - *size;
    }

    memcpy(templateData + *size, packet.data, dataLen);
    *size += dataLen;
  }

  return AS608_OK;
}

uint8_t downloadTemplate(uint8_t slot, uint8_t *templateData, uint16_t size) {
  AS608Packet packet;
  packet.data[0] = AS608_DOWNCHAR;
  packet.data[1] = slot;

  writePacket(AS608_ADDRESS, AS608_COMMANDPACKET, 2, packet.data);


  if (readPacket(&packet) <= 0 || packet.data[0] != AS608_OK) {
    return packet.data[0];
  }


  uint16_t offset = 0;
  while (offset < size) {
    uint16_t packetSize = min(128, size - offset);  
    bool isLastPacket = (offset + packetSize >= size);

    uint8_t packetType = isLastPacket ? AS608_ENDDATAPACKET : AS608_DATAPACKET;
    writePacket(AS608_ADDRESS, packetType, packetSize, templateData + offset);

    offset += packetSize;
    delay(10);  
  }

  return AS608_OK;
}

uint8_t emptyDatabase() {
  AS608Packet packet;
  packet.data[0] = AS608_EMPTY;

  writePacket(AS608_ADDRESS, AS608_COMMANDPACKET, 1, packet.data);

  if (readPacket(&packet) > 0) {
    return packet.data[0];
  }
  return 0xFF;
}



void writePacket(uint32_t address, uint8_t packetType, uint16_t length, uint8_t *data) {

  AS608Serial.write(0xEF);
  AS608Serial.write(0x01);


  AS608Serial.write((address >> 24) & 0xFF);
  AS608Serial.write((address >> 16) & 0xFF);
  AS608Serial.write((address >> 8) & 0xFF);
  AS608Serial.write(address & 0xFF);


  AS608Serial.write(packetType);


  uint16_t totalLength = length + 2;
  AS608Serial.write((totalLength >> 8) & 0xFF);
  AS608Serial.write(totalLength & 0xFF);


  uint16_t sum = packetType + ((totalLength >> 8) & 0xFF) + (totalLength & 0xFF);
  for (uint16_t i = 0; i < length; i++) {
    AS608Serial.write(data[i]);
    sum += data[i];
  }


  AS608Serial.write((sum >> 8) & 0xFF);
  AS608Serial.write(sum & 0xFF);
}

int readPacket(AS608Packet *packet, uint16_t timeout) {
  uint32_t startTime = millis();


  while (millis() - startTime < timeout) {
    if (AS608Serial.available() >= 2) {
      uint8_t b1 = AS608Serial.read();
      if (b1 == 0xEF) {
        uint8_t b2 = AS608Serial.read();
        if (b2 == 0x01) {
          packet->start = 0xEF01;
          break;
        }
      }
    }
  }

  if (packet->start != 0xEF01) {
    return -1;  
  }


  startTime = millis();
  while (AS608Serial.available() < 4 && millis() - startTime < timeout);
  if (AS608Serial.available() < 4) return -1;

  packet->address = ((uint32_t)AS608Serial.read() << 24) |
                    ((uint32_t)AS608Serial.read() << 16) |
                    ((uint32_t)AS608Serial.read() << 8) |
                    AS608Serial.read();


  startTime = millis();
  while (AS608Serial.available() < 1 && millis() - startTime < timeout);
  if (AS608Serial.available() < 1) return -1;

  packet->type = AS608Serial.read();


  startTime = millis();
  while (AS608Serial.available() < 2 && millis() - startTime < timeout);
  if (AS608Serial.available() < 2) return -1;

  packet->length = (AS608Serial.read() << 8) | AS608Serial.read();


  uint16_t dataLength = packet->length;
  if (dataLength > AS608_PACKET_MAX_SIZE) {
    return -1;  
  }

  startTime = millis();
  uint16_t bytesRead = 0;
  while (bytesRead < dataLength && millis() - startTime < timeout) {
    if (AS608Serial.available()) {
      packet->data[bytesRead++] = AS608Serial.read();
    }
  }

  if (bytesRead < dataLength) {
    return -1;  
  }


  uint16_t sum = packet->type + ((packet->length >> 8) & 0xFF) + (packet->length & 0xFF);
  for (uint16_t i = 0; i < packet->length - 2; i++) {
    sum += packet->data[i];
  }

  uint16_t receivedChecksum = (packet->data[packet->length - 2] << 8) |
                               packet->data[packet->length - 1];

  if (sum != receivedChecksum) {
    return -1;
  }

  return packet->length - 2;  
}



String bytesToHexString(uint8_t* data, uint16_t length) {
  String hexString = "";
  for (uint16_t i = 0; i < length; i++) {
    char hex[3];
    sprintf(hex, "%02X", data[i]);
    hexString += String(hex);
  }
  return hexString;
}

void hexStringToBytes(String hex, uint8_t* output, int length) {
  for (int i = 0; i < length && i * 2 < hex.length(); i++) {
    String byteString = hex.substring(i * 2, i * 2 + 2);
    output[i] = (uint8_t)strtol(byteString.c_str(), NULL, 16);
  }
}

void blinkSuccess(int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_SUCCESS_PIN, HIGH);
    delay(200);
    digitalWrite(LED_SUCCESS_PIN, LOW);
    delay(200);
  }
}

void blinkError(int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_ERROR_PIN, HIGH);
    delay(500);
    digitalWrite(LED_ERROR_PIN, LOW);
    delay(200);
  }
}

