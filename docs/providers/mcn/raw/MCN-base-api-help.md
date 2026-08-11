Методы API → Base : MCN Telecom Support 

      

      

      

      

       
  
  
  
  
  
  
  
  
  
  
  
  
 

        

        

        

        
 

  

  

  

    
  

  

  

  

  

  

  
  

  

    

      
Переход к главному содержимому

    

  

  
    

      

        

    

      

      
MCN Telecom Support

   

        

  

  

  

        

          

            
              

                

                  

 Главная
                

              

            
              

                

                  

 База знаний
                

              

            
            

             
            

          

          

            

    

      
Вход

    

    
      

        
Регистрация

      

    

            

             
Russian

 
 
English

 
 
Russian

 

            

          

        

      

    

    

  

    

    

      

       

         

    

        
          
            
              

Главная

            
          
            
              

База знаний

            
          
            
              

Интеграции

            
          
            
              

Методы API

            
          
            
              

                

                  ...
                

                

                  
                    
                  
                    
                      

База знаний

                    
                  
                    
                      

Интеграции

                    
                  
                    
                      

Методы API

                    
                  
                    
                  
                

              

              
Методы API → Base

            
          
        
    

        

        

          
Для поиска поставьте запрос в кавычки!

          

  

    

      

      

    

    

      

    

    

      

        

          Все
        

        
          

            Статьи
          

        
        
        
      

      

      

        

          

            

Предыдущие поисковые запросы

            

Очистить все

          

          
Предыдущие поисковые запросы отсутствуют

          

        

        

          

 Популярные статьи

          

        

        

          

          

            

Статьи

            

Посмотреть все

          

          

        

        

          

          

            

Темы

            

Посмотреть все

          

          

        

        

          

          

            

Заявки

            

Посмотреть все

          

          

        

      

      

        

        
Извините, ничего не нашлось по теме 
 

      

    

  

        

      

    

  

  

    

      

        

          

        

        

          
Методы API → Base

          

   Изменено Пт, 4 Окт, 2024 на 12:35 PM 

        

      

    

  

  

    

       

 
      

        

          

            

Чтобы воспользоваться методами API, перейдите в раздел Интеграции → вкладка 
Методы API
.

Затем в правом меню выберите нужный тип API — 

«Base»

.

&nbsp;

User

POST/api/protected/api/user/search
 User information — Поиск информации о пользователе по заданным критериям.

POST/api/protected/api/user/searchAll
 Users information — Поиск информации о всех пользователях.

GET/api/protected/api/user/accountList
 Account List — Получение списка аккаунтов пользователя.

POST/api/protected/api/user/addRole
 Add a role to the user — Добавление роли пользователю.

POST/api/protected/api/user/removeUserFromContract
 Remove users from contract — Удаление пользователя из контракта.

GET/api/protected/api/user/getUsersForCoreOwner
 All users in the owners contracts — Получение всех пользователей в контрактах владельца.

GET/api/protected/api/user/info
 Get user info — Получение информации о пользователе.

PATCH/api/protected/api/user/verificationCodeChannels
 Update auth source — Обновление источника аутентификации.

GET/api/protected/api/user/avatar
 Get user avatar — Получение аватара пользователя.

POST/api/protected/api/user/avatar
 Upload user avatar — Загрузка аватара пользователя.

DELETE/api/protected/api/user/avatar
 Delete user avatar — Удаление аватара пользователя.

PATCH/api/protected/api/user/sip-account/{sipId}
 Update default sip account — Обновление SIP-аккаунта по умолчанию.

POST/api/protected/api/user/getRoles
 Roles of the current user in all contracts — Получение ролей текущего пользователя во всех контрактах.

POST/api/protected/api/user/findByEmail
 User — Поиск пользователя по электронной почте.

POST/api/protected/api/user/create
 New user — Создание нового пользователя.

POST/api/protected/api/user/update
 Updated user — Обновление информации о пользователе.

GET/api/protected/api/user/getUsersByContract/{id}
 Users in contract — Получение списка пользователей в указанном контракте.

GET/api/protected/api/user/getProductsByContract/{id}
 Products of a user in specified contract — Получение продуктов/услуг пользователя в указанном контракте.

POST/api/protected/api/user/getRolesMulti
 Roles of users — Получение ролей пользователей.

GET/api/protected/api/user/getUsers
 Users by account id — Получение пользователей по идентификатору аккаунта.

POST/api/protected/api/user/setPassword
 Password for a new user — Установка пароля для нового пользователя.

POST/api/protected/api/user/addRoles
 — Добавление нескольких ролей пользователю.

POST/api/protected/api/user/removeRoles
 — Удаление ролей у пользователя.

DELETE/api/protected/api/user/roleByProduct
 delete role — Удаление роли по продукту.

POST/api/protected/api/user/updatePhoneStart
 Sends a verification code — Отправка кода верификации на указанный номер.

POST/api/protected/api/user/updatePhoneFinish
 Checks the code from the flashcall and update phone — Проверка кода из Flash Call и обновление номера телефона пользователя.

POST/api/protected/api/user/changeAuthMethod
 New auth method — Изменение метода аутентификации.

POST/api/protected/api/user/update/card
 Updated user card — Обновление карточки пользователя.

GET/api/protected/api/user/update/card
 Updated user email — Обновление электронной почты пользователя.

POST/api/protected/api/user/blockUser
 Blocked a user — Блокировка пользователя.

POST/api/protected/api/user/copyToContract
 Copy roles of users to another contract — Копирование ролей пользователя в другой контракт.

POST/api/protected/api/user/contract/roleLevel
 Add user to contract by role Level — Добавление пользователя в контракт по уровню роли.

PATCH/api/protected/api/user/token
 Create token — Создание нового токена.

DELETE/api/protected/api/user/token
 Delete token — Удаление токена.

GET/api/protected/api/user/tokens
 Retrieved user tokens — Получение списка токенов пользователя.

PATCH/api/protected/api/user/support/fields
 Updated support user fields — Обновление полей поддержки пользователя.

Lang

GET/api/protected/api/lang/mnemonic
 Lang of user — Получение языка пользователя.

Account

GET/api/protected/api/account/getTimezone
 — Получение текущего часового пояса аккаунта.

POST/api/protected/api/account/updateTimezone
 — Обновление часового пояса аккаунта.

POST/api/protected/api/account/getFreeNumbers
 — Получение списка свободных номеров для аккаунта.

POST/api/protected/api/account/getBalance
 — Получение данных баланса аккаунта.

GET/api/protected/api/account/info
 Account info — Получение информации об аккаунте.

POST/api/protected/api/account/setShowInLk
 — Настройка видимости аккаунта в личном кабинете.

PATCH/api/protected/api/account/showcase
 — Обновление информации для витрины аккаунта.

PATCH/api/protected/api/account/{accountId}
 Updated account — Обновление информации аккаунта по его идентификатору.

GET/api/protected/api/account/session
 Get all sessions by accountId — Получение всех сессий по идентификатору аккаунта.

DELETE/api/protected/api/account/session
 Delete all sessions by account Id — Удаление всех сессий по идентификатору аккаунта.

Client

POST/api/protected/api/client/search
 Stat client structure — Поиск структуры статистики клиента.

GET/api/protected/api/client
 Stat client structure — Получение структуры статистики клиента.

GET/api/protected/api/client/contracts
 All contracts in structure — Получение всех контрактов в структуре.

GET/api/protected/api/client/accounts
 All contracts with accounts in structure

session — Получение всех контрактов с аккаунтами в структуре.

DELETE/api/protected/api/session
 Delete session — Удаление сессии.

PATCH/api/protected/api/session
 Update the current session — Обновление текущей сессии.

Contract

GET/api/protected/api/contract/access
 Get all contract access — Получение списка &nbsp;всех доступов к контракту.

PATCH/api/protected/api/contract/access/{contractId}
 Update contract_access by &nbsp;— contragentId — Обновление доступа к контракту по идентификатору контрагента.

GET/api/protected/api/contract/managers
 Get all suppots with support-manager role — Получение списка всех менеджеров с ролью «support-manager».

POST/api/protected/api/contract/manager
 Link manager to specific contract — Привязка менеджера к конкретному контракту.

POST/api/protected/api/contract/accountManager
 Link manager to specific contract — Привязка менеджера аккаунта к конкретному контракту.

GET/api/protected/api/contract/organizations
 Get all organizations — Получение списка всех организаций.

GET/api/protected/api/contract/processes
 Get all business processes — Получение списка всех бизнес-процессов.

PATCH/api/protected/api/contract/processes
 — Обновление бизнес-процессов.

PATCH/api/protected/api/contract/organization
 Link organization to specific contract — Привязка организации к конкретному контракту.

GET/api/protected/api/contract/{contractId}/accounts
 Get all accounts by contractId

vpbx — Получение всех аккаунтов по идентификатору контракта.

GET/api/protected/api/vpbx/sipdevice
 Get SipDevices — Получение списка SIP-устройств.

Contragent

GET/api/protected/api/contragent
 Contragent — Получение информации о контрагенте.

GET/api/protected/api/contragent/for-current-user
 Contragents — Получение списка контрагентов для текущего пользователя.

PATCH/api/protected/api/contragent/status/{id}
 Changed status of contragent — Изменение статуса контрагента.

PATCH/api/protected/api/contragent/{id}
 Updated data of contragent — Обновление данных контрагента.

PATCH/api/protected/api/contragent/{id}/is-lk-first
 — Обновление статуса первичного входа в личный кабинет для контрагента.

GET/api/protected/api/contragent/documents/{verificationId}
 Get verification PDF — Получение PDF документа для верификации.

GET/api/protected/api/contragent/{id}/contact-users
 Get contract owners — Получение контактных лиц владельцев контрактов.

DeviceAddress

POST/api/protected/api/device-address
 Create device address — Создание нового адреса устройства.

GET/api/protected/api/device-address
 Get device address — Получение списка адресов устройств.

GET/api/protected/api/device-address/byNumber
 Get by number — Получение адреса устройства по номеру.

GET/api/protected/api/device-address/{id}
 Get device address by id — Получение адреса устройства по его идентификатору.

PATCH/api/protected/api/device-address/{id}
 Update device address by id — Обновление адреса устройства по его идентификатору.

DELETE/api/protected/api/device-address/{id}
 Delete device address by id — Удаление адреса устройства по его идентификатору.

GET/api/protected/api/device-address/{id}/file
 Get device address file by id — Получение файла с адресом устройства по идентификатору.

PUT/api/protected/api/device-address/{id}/file
 Update device address file by id — Обновление файла с адресом устройства по идентификатору.

DELETE/api/protected/api/device-address/{id}/file
 Delete device address file by id — Удаление файла с адресом устройства по идентификатору.

Number-address-country

GET/api/protected/api/number-address-country
 — Получение списка стран по адресам номеров.

POST/api/protected/api/number-address-country
 — Добавление новой записи о стране по адресу номера.

GET/api/protected/api/number-address-country/{id}
 — Получение информации о стране по идентификатору.

PATCH/api/protected/api/number-address-country/{id}
 — Обновление информации о стране по идентификатору.

DELETE/api/protected/api/number-address-country/{id}
 — Удаление информации о стране по идентификатору.

Ott

GET/api/protected/api/ott/read
 OTT client data — Получение данных OTT-клиента.

PATCH/api/protected/api/ott/update/contragent-data
 Updated Ott contragent data — Обновление данных контрагента OTT.

PATCH/api/protected/api/ott/update/device-address
 Updated Ott contragent data — Обновление адреса устройства OTT.

POST/api/protected/api/ott/update
 Updated Ott client data — Обновление данных OTT-клиента.

PATCH/api/protected/api/ott/{id}/ott-contragent
 Ott with new ott contragent id — Обновление OTT с новым идентификатором контрагента.

POST/api/protected/api/ott/{id}/reverification
 reverification command — Запуск команды повторной верификации для OTT.

POST/api/protected/api/ott-contragents
 Created Ott contragent data — Создание данных нового контрагента для OTT.

GET/api/protected/api/ott-contragents
 Get Ott contragents for current account — Получение списка контрагентов OTT для текущего аккаунта.

PATCH/api/protected/api/ott-contragents/bulk
 Changed Ott contragent status — Массовое изменение статусов контрагентов OTT.

Equipment-user

GET/api/protected/api/equipment-user
 Get all equipment users — Получить список пользователей оборудования.

POST/api/protected/api/equipment-user
 Create equipment user — Создать пользователя оборудования.

GET/api/protected/api/equipment-user/log
 Create equipment user log — Создать журнал действий пользователя оборудования.

GET/api/protected/api/equipment-user/{id}
 Get equipment user by Id — Получить пользователя оборудования по ID.

PATCH/api/protected/api/equipment-user/{id}
 Update equipment user by Id — Обновить пользователя оборудования по ID.

DELETE/api/protected/api/equipment-user/{id}
 Delete equipment user by Id — Удалить пользователя оборудования по ID.

Online-status

GET/api/protected/api/online-status
 — Получить статус онлайн.

POST/api/protected/api/online-status
 — Создать новый статус онлайн.

PATCH/api/protected/api/online-status/{statusId}
 — Обновить статус онлайн по ID.

PATCH/api/protected/api/online-status/user/{statusId}/status
 — Обновить статус онлайн пользователя по ID.

Product

GET/api/protected/api/product/get_topbar_product
 Products of platforma for topbar — Получение продуктов платформы для топбара .

GET/api/protected/api/product/get_dashboard_product
 Products of platforma for dashboard — Получение продуктов платформы для дашборда.

PATCH/api/protected/api/product/platform/image/{platformProductId}
 — Обновление изображения продукта платформы по ID.

GET/api/protected/api/product/platform
 — Получение списка продуктов платформы.

POST/api/protected/api/product/platform
 — Создание продукта для платформы.

PATCH/api/protected/api/product/platform/{platformProductId}
 — Обновление продукта платформы по ID.

GET/api/protected/api/product/stat
 — Получение статистики продуктов.

POST/api/protected/api/product/stat
 — Создание записи статистики продукта.

PATCH/api/protected/api/product/stat/{statProductId}
 — Обновление статистики продукта по ID.

GET/api/protected/api/product/dashboard/{dashboardProductId}
 Retrieve a single DashboardProduct — Получение одного продукта панели управления по ID.

PATCH/api/protected/api/product/dashboard/{dashboardProductId}
 Update a single DashboardProduct — Обновление продукта панели управления по ID.

PUT/api/protected/api/product/dashboard/{dashboardProductId}
 Replace a single DashboardProduct — Замена продукта панели управления по ID.

DELETE/api/protected/api/product/dashboard/{dashboardProductId}
 Delete a single DashboardProduct — Удаление продукта панели управления по ID.

GET/api/protected/api/product/dashboard
 Retrieve multiple DashboardProducts — Получение списка продуктов панели управления.

POST/api/protected/api/product/dashboard
 Create a single DashboardProduct — Создание одного продукта для панели управления.

POST/api/protected/api/product/dashboard/bulk
 Create multiple DashboardProducts — Массовое создание продуктов для панели управления.

Role

GET/api/protected/api/role/all
 All roles — Получить все роли.

GET/api/protected/api/role
 All roles — Получить список всех ролей.

POST/api/protected/api/role
 Create the role — Создать новую роль.

GET/api/protected/api/role/{roleId}
 Get role by ID — Получить роль по ID.

PATCH/api/protected/api/role/{roleId}
 Update the role — Обновить роль по ID.

DELETE/api/protected/api/role/{roleId}
 Delte the role — Удалить роль по ID.

Permission

GET/api/protected/api/access-control/resources
 Retrieved all resources — Получить все ресурсы.

POST/api/protected/api/access-control/resources
 Created resource — Создать ресурс.

PATCH/api/protected/api/access-control/resources/{id}
 Updated resource — Обновить ресурс по ID.

GET/api/protected/api/access-control/resources/{resourceId}
 Retrieved resource by ID — Получить ресурс по ID.

GET/api/protected/api/access-control/roles/{roleId}
 Retrieved role permissions — Получить разрешения роли по ID.

POST/api/protected/api/access-control/permissions
 Created permission — Создать разрешение.

PATCH/api/protected/api/access-control/permissions/{id}
 Update permission — Обновить разрешение по ID.

DELETE/api/protected/api/access-control/permissions/{id}
 Deleted resource — Удалить разрешение по ID.

POST/api/protected/api/access-control/roles/{roleId}/permissions
 Added permission to existed role — Добавить разрешение к существующей роли.

DELETE/api/protected/api/access-control/roles/{roleId}/permissions
 Deleted permission from existed role — Удалить разрешение из существующей роли.

GET/api/protected/api/access-control/roles
 Retrived all roles permissions — Получить все роли с их разрешениями.

GET/api/protected/api/access-control/user-sets
 Retrived all user sets with permissions — Получить все пользовательские наборы с разрешениями.

POST/api/protected/api/access-control/user-sets
 Retrived all user sets with permissions — Создать пользовательский набор с разрешениями.

GET/api/protected/api/access-control/resource-sets
 Retrived all user sets with permissions — Получить все наборы ресурсов с разрешениями.

POST/api/protected/api/access-control/resource-sets
 Created resource set — Создать набор ресурсов.

PATCH/api/protected/api/access-control/resource-sets/{id}
 Update resource set by id — Обновить набор ресурсов по ID.

POST/api/protected/api/access-control/user-sets/{id}/permissions
 Retrived all user sets with permissions — Добавить разрешения в пользовательский набор.

DELETE/api/protected/api/access-control/user-sets/{id}/permissions
 Retrived all user sets with permissions — Удалить разрешения из пользовательского набора.

DELETE/api/protected/api/access-control/user-sets/{id}
 Retrived all user sets with permissions — Удалить пользовательский набор разрешений.

Auth

GET/api/protected/api/auth/account/{accountId}
 — Получить информацию об аккаунте по его ID.

GET/api/protected/api/auth/info
 Get authinfo — Получить информацию об авторизации.

Partner

GET/api/protected/api/partner
 Get partners — Получить список партнеров.

GET/api/protected/api/partner/clients
 Get partner clients — Получить список клиентов партнера.

GET/api/protected/api/partner/partnerSettings
 Get partner settings — Получить настройки партнера.

POST/api/protected/api/partner/partnerSettings
 Create partner settings — Создать настройки партнера.

PATCH/api/protected/api/partner/partnerSettings
 Update partner settings — Обновить настройки партнера.

GET/api/protected/api/partner/partnerSettings/logo
 Upload the logo — Получить логотип.

POST/api/protected/api/partner/partnerSettings/logo
 Upload the logo — Загрузить логотип.

DELETE/api/protected/api/partner/partnerSettings/logo
 Delete the logo — Удалить логотип.

GET/api/protected/api/partner/partnerSettings/logoMobile
 Get mobile logo — Получить мобильный логотип.

POST/api/protected/api/partner/partnerSettings/logoMobile
 Upload the logo — Загрузить мобильный логотип.

DELETE/api/protected/api/partner/partnerSettings/logoMobile
 Delete the mobile logo — Удалить мобильный логотип.

GET/api/protected/api/partner/partnerApps
 Get client — &nbsp;Получить список всех приложений клиента.

POST/api/protected/api/partner/partnerApps
 Create a new client — Создать новое приложение клиента.

PATCH/api/protected/api/partner/partnerApps
 Update client — Обновить приложение клиента.

PATCH/api/protected/api/partner/partnerApps/webhook
 Set webhook — Установить вебхук.

POST/api/protected/api/partner/partnerApps/webhook
 Test webhook — Тестировать вебхук.

PATCH/api/protected/api/partner/partnerApps/secret
 Generate a new secret — Сгенерировать новый токен.

Alert

GET/api/protected/api/alert
 Get alerts — Получить список всех предупреждений.

Vat

GET/api/protected/api/vat
 Get data from Vat — Получить данные из модуля НДС (VAT).

Document

GET/api/protected/api/document/client_scans
 Get all client documents — Получить все документы клиента.

POST/api/protected/api/document/client_scans
 Upload a new client document — Загрузить новый документ клиента.

GET/api/protected/api/document/client_scans/{fileId}
 Get specific client document by FileID — Получить документ клиента по ID файла.

Support

GET/api/protected/api/support/search
 Get contragents by meta — Получить контрагентов по метаданным.

GET/api/protected/api/support/client
 Get clients for manager — Получить список клиентов для менеджера.

GET/api/protected/api/support/contacts
 Get contacts from addressbook — Получить контакты из адресной книги.

GET/api/protected/api/support/jira/issues
 Retrieved issues from JIRA — Получить список задач из JIRA.

POST/api/protected/api/support/jira/issue
 Created issue in JIRA — Создать новую задачу в JIRA.

GET/api/protected/api/support/jira/issue/{issueId}
 Retrieved issue — Получить информацию о конкретной задаче используя её ID.

PATCH/api/protected/api/support/jira/issue/{issueId}
 Update issue — Обновить информацию о задаче используя её ID.

PATCH/api/protected/api/support/jira/issue/{issueId}/status
 Changed issue status — Изменить статус задачи используя её ID.

GET/api/protected/api/support/jira/user
 Get all users — Получить список всех пользователей.

Billing

GET/api/protected/api/billing/receiptUrl
 Retrieved receipt url — Получить URL квитанции.

GET/api/protected/api/billing/invoice/{statBillId}
 Retrieved invoice by statId — Получить счет по указанному статическому ID счета.

Notification

GET/api/protected/api/notification-alert
 Retrieve notification alerts — Получить уведомления.

POST/api/protected/api/notification-alert
 Created notification alert — Создать новое уведомление.

GET/api/protected/api/notification-alert/{id}
 Get notification alert — Получить уведомление по ID.

PATCH/api/protected/api/notification-alert/{id}
 Updated notification alert — Обновить уведомление по ID.

Tag

GET/api/protected/api/tag
 Get all tags — Получить все теги.

POST/api/protected/api/tag
 Create tag — Создать новый тег.

GET/api/protected/api/tag/{id}
 Get one tag by ID — Получить тег по его ID.

PATCH/api/protected/api/tag/{id}
 Update tag by ID — Обновить тег по его ID.

DELETE/api/protected/api/tag/{id}
 Delete tag by ID — Удалить тег по его ID.

POST/api/protected/api/tag/{entityType}/{entityId}/{tagId}
 Assign tag to specific entity type and entity id — Назначить тег определенному типу сущности и ID сущности.

DELETE/api/protected/api/tag/{entityType}/{entityId}/{tagId}
 Deassign tag from specific entity type and entity id — Удалить назначение тега для определенного типа сущности и ID сущности.

Также см.:

Методы API → Интеграция

Методы API → Автозвонки

Методы API → API ЛК

Методы API → Интеграции v2

Методы API → Адресная книга

Методы API → Виртуальная АТС

            

          

          

  

    

      
Статья помогла?

    

    

      

  

Нет
  

      

  

Да
  

    

  

  

    

      

  

  

  

  

  

  

  

  

  

  

  

  

  

  

  

  

  

  

      
Отлично!

      
Спасибо за ваш отзыв

    

  

  

    

      

  

  

  

  

  

  

  

  

  

  

  

  

  

  

  

  

  

  

  

  

      
Извините, что не удалось помочь!

      
Спасибо за ваш отзыв

      

        
         
         

	
		

			Ваш электронный адрес
			
				
*

			
		

		
	

	
	

	

	

   	

	

  

        
        
Расскажите, как мы можем улучшить эту статью!
 
*

        

          
            
            

	

	
	

	
       

	

	

   	

	
		

			Нужно больше информации
			
		

		
	

  

          
            
            

	

	
	

	
       

	

	

   	

	
		

			Сложный для понимания
			
		

		
	

  

          
            
            

	

	
	

	
       

	

	

   	

	
		

			Неточное или неподходящее содержимое
			
		

		
	

  

          
            
            

	

	
	

	
       

	

	

   	

	
		

			Ссылка отсутствует или недействительна
			
		

		
	

  

          
        

        

          Выберите хотя бы одну причину
        

        

  
		

			Оставьте комментарий
			
		

		
  

  

  

        
          

  

    

      
        

        

      
      

        Требуется проверка CAPTCHA.
      

    

  

        

        

  Отмена
  

        

  Отправить
  

      

    

  

  

    

      


















      
Комментарий отправлен

      
Мы ценим вашу помощь и постараемся исправить статью

    

  

        

        

          

            

             

Print

            

            

              
Статьи в этой папке:

              

                
                 

                  
Альфа номера

                 

                
                 

                  
A2P SMS

                 

                
                 

                  
Сервис сокращения ссылок (URL)

                 

                
                 

                  
Методы авторизации к API

                 

                
              

            

            
              

                
Вам может понравиться

                

                  
                   

                    
Методы API → SMS

                   

                  
                   

                    
Методы API → API ЛК

                   

                  
                   

                    
Методы API → Интеграции v2

                   

                  
                   

                    
Методы API → Интеграция

                   

                  
                

              

            
          

        

      

    

  

  

  

    

X

  

  

    

      

      

    

  

  

    
0 из 0

    

    

    

  

 

   

     

       

+7(495)109-94-96