// --- AWS COGNITO AYARLARI ---
const poolData = {
    UserPoolId: 'eu-north-1_m0XhEtHBh', 
    ClientId: '5eevgabapncn6qr8qrpci9s75m'
};

const userPool = new AmazonCognitoIdentity.CognitoUserPool(poolData);

document.getElementById('loginForm').addEventListener('submit', function(event) {
    event.preventDefault();

    const usernameInput = document.getElementById('username').value;
    const passwordInput = document.getElementById('password').value;
    const errorDiv = document.getElementById('loginError');
    
    errorDiv.innerText = "Giriş yapılıyor...";

    const authenticationDetails = new AmazonCognitoIdentity.AuthenticationDetails({
        Username: usernameInput,
        Password: passwordInput,
    });

    const cognitoUser = new AmazonCognitoIdentity.CognitoUser({
        Username: usernameInput,
        Pool: userPool
    });

    cognitoUser.authenticateUser(authenticationDetails, {
        onSuccess: function (result) {
            localStorage.setItem('accessToken', result.getAccessToken().getJwtToken());
            localStorage.setItem('idToken', result.getIdToken().getJwtToken());
            localStorage.setItem('username', usernameInput);
            window.location.href = "dashboard.html";
        },
        onFailure: function(err) {
            console.error("Giriş Hatası:", err);
            errorDiv.innerText = "Giriş başarısız: " + err.message;
        },
        newPasswordRequired: function(userAttributes, requiredAttributes) {
            const newPassword = prompt("İlk giriş için yeni şifre belirleyin:");
            if(newPassword) {
                cognitoUser.completeNewPasswordChallenge(newPassword, {}, this);
            } else {
                errorDiv.innerText = "Şifre değişimi iptal edildi.";
            }
        }
    });
});