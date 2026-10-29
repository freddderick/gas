import UIKit
import UserNotifications

/// Receives the APNs device token and notification taps, and hands both to
/// the AppModel.
@MainActor
final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    private weak var model: AppModel?
    private var pendingDeepLink: URL?
    private var pendingToken: String?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    /// Called once the SwiftUI scene exists. Anything that arrived before
    /// (a cold launch from a notification tap) is replayed here.
    func attach(_ model: AppModel) {
        self.model = model
        if let token = pendingToken {
            pendingToken = nil
            model.updatePushToken(token)
        }
        if let url = pendingDeepLink {
            pendingDeepLink = nil
            model.handle(url: url)
        }
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        if let model {
            model.updatePushToken(token)
        } else {
            pendingToken = token
        }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        // Simulators without push support land here. Alerts stay off until a
        // token arrives; Settings shows the notification status.
    }

    // Show alerts as banners even while the app is open.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        if let model {
            Task { await model.refresh() }
        }
        return [.banner, .list, .sound]
    }

    // A tap on an alert opens the pressure detail screen.
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        let link = response.notification.request.content.userInfo["deep_link"] as? String
        let url = link.flatMap { URL(string: $0) } ?? AppModel.detailURL
        if let model {
            model.handle(url: url)
        } else {
            pendingDeepLink = url
        }
    }
}
