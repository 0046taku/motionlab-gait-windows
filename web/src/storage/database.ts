import type { Patient, StorageEstimate, VideoStudy } from "../domain/models";

const DATABASE_NAME = "motionlab-gait-local";
const DATABASE_VERSION = 1;

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("ローカル保存に失敗しました。"));
  });
}

export class MotionLabDatabase {
  private readonly connection: Promise<IDBDatabase>;

  constructor() {
    this.connection = this.open();
  }

  private open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains("patients")) {
          const patients = database.createObjectStore("patients", { keyPath: "id" });
          patients.createIndex("patientCode", "patientCode", { unique: true });
        }
        if (!database.objectStoreNames.contains("videos")) {
          const videos = database.createObjectStore("videos", { keyPath: "id" });
          videos.createIndex("patientId", "patientId", { unique: false });
          videos.createIndex("createdAt", "createdAt", { unique: false });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("IndexedDBを開けません。"));
    });
  }

  async listPatients(): Promise<Patient[]> {
    const database = await this.connection;
    const values = await requestResult(
      database.transaction("patients", "readonly").objectStore("patients").getAll()
    );
    return values.sort((a, b) => a.patientCode.localeCompare(b.patientCode, "ja"));
  }

  async savePatient(patient: Patient): Promise<void> {
    const database = await this.connection;
    await requestResult(
      database.transaction("patients", "readwrite").objectStore("patients").put(patient)
    );
  }

  async listVideos(patientId: string): Promise<VideoStudy[]> {
    const database = await this.connection;
    const index = database.transaction("videos", "readonly").objectStore("videos").index("patientId");
    const values = await requestResult(index.getAll(patientId));
    return values.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }

  async getVideo(id: string): Promise<VideoStudy | undefined> {
    const database = await this.connection;
    return requestResult(
      database.transaction("videos", "readonly").objectStore("videos").get(id)
    );
  }

  async saveVideo(video: VideoStudy): Promise<void> {
    const existing = await this.getVideo(video.id);
    const estimate = await this.storageEstimate();
    const additionalBytes = Math.max(0, video.video.size - (existing?.video.size ?? 0));
    if (estimate.quota > 0 && estimate.usage + additionalBytes > estimate.quota * 0.95) {
      throw new Error("端末の保存容量が不足しています。不要な動画を削除してください。");
    }
    const database = await this.connection;
    await requestResult(
      database.transaction("videos", "readwrite").objectStore("videos").put(video)
    );
  }

  async storageEstimate(): Promise<StorageEstimate> {
    const estimate = await navigator.storage?.estimate?.();
    return { usage: estimate?.usage ?? 0, quota: estimate?.quota ?? 0 };
  }

  async requestPersistence(): Promise<boolean> {
    if (!navigator.storage?.persist) return false;
    return navigator.storage.persist();
  }
}
